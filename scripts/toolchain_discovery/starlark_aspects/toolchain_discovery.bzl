ToolchainInfo = provider(
    fields = {
        "toolchains": "Dict of toolchain_type -> resolved toolchain info",
        "repositories": "Set of external repository names",
    }
)

def _toolchain_discovery_aspect_impl(target, ctx):
    """Aspect to discover all resolved toolchains"""
    toolchains = {}
    repositories = []
    
    # Collect toolchain info from current target
    if hasattr(ctx, "toolchains"):
        for toolchain_type, toolchain in ctx.toolchains.items():
            if toolchain:
                repo_name = toolchain.label.workspace_name
                toolchains[str(toolchain_type)] = {
                    "label": str(toolchain.label),
                    "repository": repo_name,
                }
                if repo_name:
                    repositories.append(repo_name)
    
    # Merge with dependencies
    for dep in ctx.rule.attr.deps:
        if ToolchainInfo in dep:
            for tt, info in dep[ToolchainInfo].toolchains.items():
                if tt not in toolchains:
                    toolchains[tt] = info
            repositories.extend(dep[ToolchainInfo].repositories)
    
    return [ToolchainInfo(
        toolchains = toolchains,
        repositories = depset(repositories).to_list(),
    )]

toolchain_discovery_aspect = aspect(
    implementation = _toolchain_discovery_aspect_impl,
    attr_aspects = ["*"],
    toolchains = [
        "@bazel_tools//tools/cpp:toolchain_type",
        "@bazel_tools//tools/jdk:toolchain_type",
        "@rules_go//go:toolchain_type",
        "@aspect_rules_js//js:toolchain_type",
        "@rules_python//python:toolchain_type",
        "@rules_rust//rust:toolchain_type",
    ],
)
