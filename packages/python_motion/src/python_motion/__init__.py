"""Public entry for the motion asset service."""

from .service import BuildRequest, build_assets, main


class MotionAssetService:
    def build(self, manifest_path: str, out_dir: str, only_sfx: bool = False, only_bookends: bool = False, animatic: bool = False) -> dict:
        return build_assets(BuildRequest(manifest_path, out_dir, only_sfx, only_bookends, animatic))


__all__ = ["MotionAssetService", "main"]
