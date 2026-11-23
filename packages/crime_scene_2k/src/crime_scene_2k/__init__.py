"""2K still tour service."""

from .cli import main, render_manifest


class CrimeScene2KService:
    def render(self, manifest_path: str, stills_dir: str, out_dir: str, scene_id: str | None = None) -> dict:
        return render_manifest(manifest_path, stills_dir, out_dir, scene_id)


__all__ = ["CrimeScene2KService", "main", "render_manifest"]
