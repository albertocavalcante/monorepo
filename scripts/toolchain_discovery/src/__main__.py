#!/usr/bin/env -S uv --quiet run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic>=2.0",
#   "httpx>=0.25.0",
#   "rich>=13.0.0",
# ]
# ///
# type: ignore[import]

import argparse
import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

console = Console()

class ToolchainArtifact(BaseModel):
    """Represents a toolchain artifact to be mirrored"""
    url: str
    sha256: str
    platform: str
    toolchain_type: str
    repository_name: str
    strip_prefix: Optional[str] = None

class BazelToolchainProfiler:
    def __init__(self, platforms: List[str], target_dir: str = ".", clean_mode: bool = False):
        self.platforms = platforms
        self.target_dir = Path(target_dir).resolve()
        self.artifacts: List[ToolchainArtifact] = []
        self.temp_platforms_created = False
        self.original_build_content = None
        self.clean_mode = clean_mode
        self.temp_aspect_created = False
        self.aspect_dir = None
        
    async def profile_all_platforms(self) -> None:
        """Main entry point to profile all platforms"""
        console.print("[bold blue]Starting Bazel toolchain profiling...[/bold blue]")
        
        try:
            # Step 1: Discover or create platforms
            await self._ensure_platforms()
            
            # Step 2: Set up workspace rules log
            with tempfile.NamedTemporaryFile(suffix=".bin") as log_file:
                # Step 3: Run analysis for each platform
                for platform in self.platforms:
                    console.print(f"\n[yellow]Analyzing platform: {platform}[/yellow]")
                    await self._analyze_platform(platform, log_file.name)
                
                # Step 4: Parse workspace log
                self._parse_workspace_log(log_file.name)
            
            # Step 5: Generate manifest
            self._generate_manifest()
        finally:
            # Step 6: Cleanup temporary platforms
            self._cleanup_temp_platforms()
    
    async def _analyze_platform(self, platform: str, log_path: str) -> None:
        """Analyze toolchains for a specific platform"""
        if self.clean_mode:
            # Clean to force fresh fetches (optional, slower)
            subprocess.run(["bazel", "--batch", "clean", "--expunge"], check=True, cwd=self.target_dir)
        
        # Build with platform override and workspace logging
        cmd = [
            "bazel", 
            "--batch",
            "build",
            f"--platforms={platform}",
            f"--experimental_workspace_rules_log_file={log_path}",
            "--repository_cache=",  # Force fresh repository downloads
            "--toolchain_resolution_debug=.*",
            "//...",  # Build everything to trigger all toolchains
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.target_dir)
        
        # Parse toolchain resolution output
        self._parse_toolchain_debug(result.stderr, platform)
    
    def _parse_toolchain_debug(self, output: str, platform: str) -> None:
        """Parse --toolchain_resolution_debug output"""
        for line in output.split('\n'):
            if "Selected toolchain" in line:
                # Extract repository name from debug output
                parts = line.split()
                for part in parts:
                    if part.startswith("@") and "//" in part:
                        repo_name = part.split("//")[0].lstrip("@")
                        console.print(f"  Found toolchain repository: [green]{repo_name}[/green]")
                        # Query for repository definition
                        self._query_repository(repo_name, platform)
    
    def _query_repository(self, repo_name: str, platform: str) -> None:
        """Query repository definition to extract URLs"""
        try:
            result = subprocess.run(
                ["bazel", "--batch", "query", f"@{repo_name}//...", "--output=build"],
                capture_output=True, text=True, check=True, cwd=self.target_dir
            )
            
            # Parse http_archive attributes
            definition = result.stdout
            if "http_archive" in definition:
                artifact = self._parse_http_archive(definition, repo_name, platform)
                if artifact:
                    self.artifacts.append(artifact)
        except subprocess.CalledProcessError:
            console.print(f"  [red]Failed to query {repo_name}[/red]")
    
    def _parse_http_archive(self, definition: str, repo_name: str, platform: str) -> Optional[ToolchainArtifact]:
        """Parse http_archive definition"""
        urls = []
        sha256 = ""
        strip_prefix = None
        
        for line in definition.split('\n'):
            line = line.strip()
            if line.startswith('"url"'):
                # Single URL format
                url = line.split('"')[3]
                urls = [url]
            elif line.startswith('"urls"'):
                # Multiple URLs format
                # Parse list of URLs (simplified)
                pass
            elif line.startswith('"sha256"'):
                sha256 = line.split('"')[3]
            elif line.startswith('"strip_prefix"'):
                strip_prefix = line.split('"')[3]
        
        if urls and sha256:
            return ToolchainArtifact(
                url=urls[0],
                sha256=sha256,
                platform=platform,
                toolchain_type="unknown",  # Would need aspect to determine
                repository_name=repo_name,
                strip_prefix=strip_prefix,
            )
        return None
    
    def _parse_workspace_log(self, log_path: str) -> None:
        """Parse the experimental workspace rules log"""
        # This would use the workspacelog parser tool
        # For now, this is a placeholder
        pass
    
    def _generate_manifest(self) -> None:
        """Generate final manifest file"""
        manifest_path = self.target_dir / "toolchain_manifest.json"
        
        # Group by platform
        by_platform: Dict[str, List[Dict]] = {}
        for artifact in self.artifacts:
            if artifact.platform not in by_platform:
                by_platform[artifact.platform] = []
            by_platform[artifact.platform].append(artifact.model_dump())
        
        with open(manifest_path, "w") as f:
            json.dump(by_platform, f, indent=2)
        
        # Display summary table
        table = Table(title="Toolchain Artifacts Summary")
        table.add_column("Platform", style="cyan")
        table.add_column("Repository", style="green")
        table.add_column("URL", style="blue")
        
        for artifact in self.artifacts:
            table.add_row(
                artifact.platform,
                artifact.repository_name,
                artifact.url[:60] + "..." if len(artifact.url) > 60 else artifact.url
            )
        
        console.print(table)
        console.print(f"\n[green]✓ Manifest written to {manifest_path}[/green]")
    
    async def _ensure_platforms(self) -> None:
        """Discover existing platforms or create temporary ones"""
        discovered_platforms = await self._discover_platforms()
        
        if discovered_platforms:
            console.print(f"[green]Found {len(discovered_platforms)} existing platforms[/green]")
            self.platforms = discovered_platforms
        else:
            console.print("[yellow]No platforms found, creating temporary platforms[/yellow]")
            await self._create_temp_platforms()
    
    async def _discover_platforms(self) -> List[str]:
        """Query target workspace for existing platform definitions"""
        try:
            result = subprocess.run(
                ["bazel", "--batch", "query", "kind(platform, //...)", "--output=label"],
                capture_output=True, text=True, check=True, cwd=self.target_dir
            )
            
            platforms = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            # Filter to relevant platforms only
            relevant_platforms = [p for p in platforms if any(
                arch in p.lower() for arch in ['linux', 'darwin', 'windows', 'amd64', 'arm64', 'x86_64']
            )]
            
            return relevant_platforms[:4]  # Limit to 4 platforms max
        except subprocess.CalledProcessError:
            return []
    
    async def _create_temp_platforms(self) -> None:
        """Create temporary platform definitions in target workspace"""
        build_file_path = self.target_dir / "BUILD.bazel"
        build_file_alt_path = self.target_dir / "BUILD"
        
        # Choose existing BUILD file or create BUILD.bazel
        if build_file_path.exists():
            target_build_file = build_file_path
        elif build_file_alt_path.exists():
            target_build_file = build_file_alt_path
        else:
            target_build_file = build_file_path
        
        # Store original content for cleanup
        if target_build_file.exists():
            self.original_build_content = target_build_file.read_text()
        else:
            self.original_build_content = None
        
        # Platform definitions (removed darwin_amd64 as requested)
        platform_defs = '''
# Temporary platform definitions for toolchain discovery
platform(
    name = "linux_amd64",
    constraint_values = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
    ],
)

platform(
    name = "linux_arm64",
    constraint_values = [
        "@platforms//os:linux",
        "@platforms//cpu:arm64",
    ],
)

platform(
    name = "darwin_arm64",
    constraint_values = [
        "@platforms//os:macos",
        "@platforms//cpu:arm64",
    ],
)

platform(
    name = "windows_amd64",
    constraint_values = [
        "@platforms//os:windows",
        "@platforms//cpu:x86_64",
    ],
)
'''
        
        # Append platform definitions
        content_to_write = ""
        if self.original_build_content:
            content_to_write = self.original_build_content + "\n" + platform_defs
        else:
            content_to_write = platform_defs
        
        target_build_file.write_text(content_to_write)
        self.temp_platforms_created = True
        
        # Update platform list to use the temporary platforms
        self.platforms = [
            # "//:linux_amd64",
            # "//:linux_arm64", 
            "//:darwin_arm64",
            # "//:windows_amd64",
        ]
        
        console.print(f"[green]Created temporary platforms in {target_build_file}[/green]")
    
    def _cleanup_temp_platforms(self) -> None:
        """Remove temporary platform definitions"""
        if not self.temp_platforms_created:
            return
        
        build_file_path = self.target_dir / "BUILD.bazel"
        build_file_alt_path = self.target_dir / "BUILD"
        
        # Find the build file we modified
        target_build_file = None
        if build_file_path.exists():
            target_build_file = build_file_path
        elif build_file_alt_path.exists():
            target_build_file = build_file_alt_path
        
        if target_build_file:
            if self.original_build_content is not None:
                # Restore original content
                target_build_file.write_text(self.original_build_content)
                console.print(f"[green]Restored original {target_build_file}[/green]")
            else:
                # Remove the file we created
                target_build_file.unlink()
                console.print(f"[green]Removed temporary {target_build_file}[/green]")

async def async_main():
    parser = argparse.ArgumentParser(description="Discover and profile Bazel toolchains")
    parser.add_argument("target_dir", nargs="?", default=".", 
                       help="Target Bazel workspace directory to analyze (default: current directory)")
    parser.add_argument("--clean", action="store_true",
                       help="Run clean --expunge before analysis (slower but more thorough)")
    args = parser.parse_args()
    
    # Default platforms - will be discovered or created temporarily
    platforms = [
        "//:linux_amd64",
        "//:linux_arm64",
        "//:darwin_arm64", 
        "//:windows_amd64",
    ]
    
    profiler = BazelToolchainProfiler(platforms, args.target_dir, args.clean)
    await profiler.profile_all_platforms()

def main():
    """Synchronous entry point for console script"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
