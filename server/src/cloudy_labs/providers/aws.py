"""AWS on Floci or moto."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

import boto3

from ..config import ACCESS_KEY_ID, API_PORT, FLOCI_PORT, HOST, MOTO_PORT, REGION, SECRET_ACCESS_KEY, home
from ..emulator.docker import DockerError
from ..emulator.stack import reachable, recreate_floci

Emulator = Literal["floci", "moto"]
# The learner's CLI and the checkers reach Floci through api-tap, so their calls show up in the
# 3D scene; labctl's own calls and the collector go straight to Floci.
PORTS: dict[str, int] = {"floci": API_PORT, "moto": MOTO_PORT}
DIRECT_PORTS: dict[str, int] = {"floci": FLOCI_PORT, "moto": MOTO_PORT}
# After a reset, moto enforces IAM. labctl spends the unauthenticated calls it allows on
# creating an admin user (CreateUser, PutUserPolicy, CreateAccessKey); the learner's CLI
# and the checkers then sign as that user.
MOTO_ADMIN_USER = "cloudy-labs-admin"
MOTO_NO_AUTH_ACTIONS = 3
ADMIN_POLICY = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}

Credentials = tuple[str, str]


def moto_credentials_file() -> Path:
    return home() / "moto-credentials.json"


class AwsProvider:
    def __init__(self, emulator: Emulator = "floci"):
        self.emulator = emulator
        self.endpoint = f"http://{HOST}:{PORTS[emulator]}"
        self.direct_endpoint = f"http://{HOST}:{DIRECT_PORTS[emulator]}"

    def credentials(self) -> Credentials:
        """The admin user on moto once a lab has started there; the emulator's fake keys otherwise."""
        if self.emulator == "moto":
            try:
                data = json.loads(moto_credentials_file().read_text())
                return data["AccessKeyId"], data["SecretAccessKey"]
            except (OSError, ValueError, KeyError):
                pass  # no moto lab started yet: moto does not enforce IAM until the first reset
        return ACCESS_KEY_ID, SECRET_ACCESS_KEY

    def client(self, service: str, credentials: Credentials | None = None, *, direct: bool = False, config: Any = None,
               session: boto3.session.Session | None = None) -> Any:
        """`credentials` lets a checker act as another IAM user, for example one the learner created.

        `direct` bypasses api-tap, for reads that must not count as learner activity. `session` is
        for a caller off the main thread, since boto3 sessions (the default one too) are not thread-safe.
        """
        key, secret = credentials or self.credentials()
        return (session or boto3).client(
            service,
            endpoint_url=self.direct_endpoint if direct else self.endpoint,
            region_name=REGION,
            aws_access_key_id=key,
            aws_secret_access_key=secret,
            config=config,
        )

    def env(self) -> dict[str, str]:
        key, secret = self.credentials()
        return {
            "AWS_ENDPOINT_URL": self.endpoint,
            "AWS_ACCESS_KEY_ID": key,
            "AWS_SECRET_ACCESS_KEY": secret,
            "AWS_DEFAULT_REGION": REGION,
            "AWS_PAGER": "",
        }

    def health(self) -> bool:
        return reachable(self.emulator)

    def reset(self) -> None:
        if self.emulator == "floci":
            # Floci keeps state in memory, so a new container starts empty.
            found = recreate_floci()
            if found.errors:
                raise DockerError("could not remove some Floci resources: " + "; ".join(found.errors))
        else:
            self._moto_post("/moto-api/reset", b"", "application/json")
            # The body must be a bare number; a JSON body makes moto answer HTTP 500.
            self._moto_post("/moto-api/reset-auth", str(MOTO_NO_AUTH_ACTIONS).encode(), "text/plain")
            self._create_moto_admin()

    def _create_moto_admin(self) -> None:
        iam = self.client("iam", (ACCESS_KEY_ID, SECRET_ACCESS_KEY))  # within the unauthenticated calls
        iam.create_user(UserName=MOTO_ADMIN_USER)
        iam.put_user_policy(UserName=MOTO_ADMIN_USER, PolicyName="admin", PolicyDocument=json.dumps(ADMIN_POLICY))
        key = iam.create_access_key(UserName=MOTO_ADMIN_USER)["AccessKey"]
        file = moto_credentials_file()
        file.parent.mkdir(parents=True, exist_ok=True)
        # Emulator-only keys, but still kept out of the repo and readable by the owner only.
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"AccessKeyId": key["AccessKeyId"], "SecretAccessKey": key["SecretAccessKey"]}, f)

    def _moto_post(self, path: str, body: bytes, content_type: str) -> None:
        req = urllib.request.Request(
            self.endpoint + path, data=body, method="POST", headers={"Content-Type": content_type}
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
        except (urllib.error.URLError, OSError) as e:
            raise DockerError(f"moto {path} failed: {e}; is the stack up (`labctl up`)?") from e
