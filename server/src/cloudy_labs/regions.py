"""AWS regions a lab may name: the commercial partition as the installed botocore knows it."""

from functools import lru_cache

import botocore.session


@lru_cache(maxsize=1)
def known_regions() -> frozenset[str]:
    return frozenset(botocore.session.get_session().get_available_regions("ec2"))


def check_region(name: str) -> str:
    if name not in known_regions():
        raise ValueError(f"{name!r} is not an AWS region botocore knows (for example ap-southeast-2)")
    return name
