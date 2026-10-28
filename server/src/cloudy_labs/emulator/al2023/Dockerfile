# Amazon Linux 2023 with what Floci installs into every EC2 instance at boot: the IMDS proxy
# needs ip, socat and curl, SSH needs sshd and scp. When they are already present Floci skips
# that per-boot network install, which can time out after 180 s.
# A newer base digest: `uv run python -m cloudy_labs.emulator.images bump-base`. Any other change
# here: the same command with --force, which bumps the image tag version alone.
FROM public.ecr.aws/amazonlinux/amazonlinux:2023@sha256:8272aee6146a36222baaf71d72ab6799770957414ac63b1e940cec58c9197188
RUN dnf install -y --allowerasing iproute socat curl ca-certificates openssh-server openssh-clients \
    && dnf clean all
