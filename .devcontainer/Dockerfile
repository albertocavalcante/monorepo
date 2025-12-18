# -----------------------------------------------------------------------------
# Dockerfile for Monorepo Development Container
# Inspired by albertocavalcante/groovy-lsp
# -----------------------------------------------------------------------------

FROM registry.access.redhat.com/ubi9/ubi-minimal:latest

# Arguments
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Tool Versions
ARG BAZELISK_VERSION=v1.25.0
ARG BUILDIFIER_VERSION=v8.2.1
ARG GH_VERSION=2.64.0

# -----------------------------------------------------------------------------
# Layer 1: Base Packages
# -----------------------------------------------------------------------------
RUN microdnf install -y \
    ca-certificates \
    curl \
    git \
    shadow-utils \
    tar \
    gzip \
    unzip \
    vi \
    findutils \
    util-linux \
    sudo \
    && microdnf clean all

# -----------------------------------------------------------------------------
# Layer 2: Bazelisk (Bazel)
# -----------------------------------------------------------------------------
RUN ARCH=$(uname -m) \
    && if [ "$ARCH" = "x86_64" ]; then BAZEL_ARCH="amd64"; else BAZEL_ARCH="arm64"; fi \
    && curl -fSL https://github.com/bazelbuild/bazelisk/releases/download/${BAZELISK_VERSION}/bazelisk-linux-${BAZEL_ARCH} -o /usr/local/bin/bazel \
    && chmod +x /usr/local/bin/bazel

# -----------------------------------------------------------------------------
# Layer 3: Buildifier
# -----------------------------------------------------------------------------
RUN ARCH=$(uname -m) \
    && if [ "$ARCH" = "x86_64" ]; then BUILDIFIER_ARCH="amd64"; else BUILDIFIER_ARCH="arm64"; fi \
    && curl -fSL https://github.com/bazelbuild/buildtools/releases/download/${BUILDIFIER_VERSION}/buildifier-linux-${BUILDIFIER_ARCH} -o /usr/local/bin/buildifier \
    && chmod +x /usr/local/bin/buildifier

# -----------------------------------------------------------------------------
# Layer 4: GitHub CLI
# -----------------------------------------------------------------------------
RUN ARCH=$(uname -m) \
    && if [ "$ARCH" = "x86_64" ]; then GH_ARCH="amd64"; else GH_ARCH="arm64"; fi \
    && curl -fSL https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${GH_ARCH}.tar.gz -o /tmp/gh.tar.gz \
    && tar -xzf /tmp/gh.tar.gz -C /tmp \
    && mv /tmp/gh_${GH_VERSION}_linux_${GH_ARCH}/bin/gh /usr/local/bin/ \
    && rm -rf /tmp/*

# -----------------------------------------------------------------------------
# Layer 5: User Setup
# -----------------------------------------------------------------------------
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

USER $USERNAME
WORKDIR /home/$USERNAME

CMD ["/bin/bash"]
