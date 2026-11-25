"""Build a simple 3D scene in Blender and render a silent clip. Blender is a separate app."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

KITS = ("overview", "porch", "document", "merge", "desk", "scale")
PICTURE_VERSION = "2"

BLENDER_SCRIPT = r'''
import math
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]


def flag(name, default):
    if name not in argv:
        return default
    return argv[argv.index(name) + 1]


out = flag("--out", "")
seconds = float(flag("--seconds", "4"))
kit = flag("--kit", "overview")
fps = int(flag("--fps", "12"))
if kit not in ("overview", "porch", "document", "merge", "desk", "scale"):
    kit = "overview"

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = max(fps * 2, int(round(seconds * fps)))
scene.render.fps = fps
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.engine = "BLENDER_WORKBENCH"
shading = scene.display.shading
shading.light = "FLAT"
shading.color_type = "MATERIAL"
try:
    shading.background_type = "VIEWPORT"
    shading.background_color = (0.62, 0.66, 0.70)
except AttributeError:
    pass


def material(name, rgb):
    made = bpy.data.materials.new(name)
    made.diffuse_color = (rgb[0], rgb[1], rgb[2], 1)
    node = made.node_tree.nodes.get("Principled BSDF") if made.node_tree else None
    if node is not None:
        node.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1)
        node.inputs["Roughness"].default_value = 0.55
    return made


PAPER = material("Paper", (0.93, 0.90, 0.82))
INK = material("Ink", (0.07, 0.08, 0.09))
WALL = material("Wall", (0.78, 0.76, 0.71))
BODY = material("Body", (0.16, 0.18, 0.22))
FOLDER = material("Folder", (0.70, 0.52, 0.26))
GROUND = material("Ground", (0.13, 0.15, 0.17))
BRASS = material("Brass", (0.74, 0.60, 0.30))
DOOR = material("Door", (0.40, 0.28, 0.20))


def cube(name, location, scale, surface):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(surface)
    return obj


def cylinder(name, location, scale, surface):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(surface)
    return obj


def plane(name, location, scale, surface):
    bpy.ops.mesh.primitive_plane_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(surface)
    return obj


plane("Ground", (0, 0, 0), (18, 18, 1), GROUND)

if kit == "porch":
    cube("Wall", (0, 2.2, 1.6), (5.2, 0.18, 3.2), WALL)
    cube("Door", (0, 2.05, 1.05), (1.1, 0.08, 2.1), DOOR)
    cube("Camera body", (1.3, 1.95, 2.3), (0.28, 0.22, 0.22), BODY)
    cylinder("Lens", (1.3, 1.7, 2.3), (0.12, 0.12, 0.28), BRASS)
    look = (0.4, 1.4, 1.4)
    start, end = (2.2, -5.6, 2.5), (0.6, -3.6, 1.9)
elif kit == "document":
    page = plane("Page", (0, 0, 0.55), (2.4, 3.2, 1), PAPER)
    page.rotation_euler = (math.radians(72), 0, 0)
    for index, height in enumerate((0.35, 0.0, -0.35)):
        bar = cube(f"Redaction {index + 1}", (0, height, 0.72), (1.5, 0.12, 0.04), INK)
        bar.rotation_euler = (math.radians(72), 0, 0)
    look = (0, 0, 0.7)
    start, end = (-1.4, -4.0, 2.4), (1.0, -2.6, 1.7)
elif kit == "merge":
    cube("Camera body", (-2.2, 0, 0.7), (0.5, 0.36, 0.36), BODY)
    cylinder("Lens", (-1.7, 0, 0.7), (0.16, 0.16, 0.4), BRASS)
    page = plane("Page", (2.2, 0, 0.7), (1.4, 1.8, 1), PAPER)
    page.rotation_euler = (math.radians(70), 0, math.radians(8))
    folder = cube("Folder", (0, 0, 0.2), (1.3, 1.0, 0.28), FOLDER)
    folder.location = (0, 0, 0.15)
    folder.keyframe_insert("location", frame=1)
    folder.location = (0, 0, 0.85)
    folder.keyframe_insert("location", frame=scene.frame_end)
    look = (0, 0, 0.7)
    start, end = (0.2, -5.4, 2.6), (0, -3.4, 1.8)
elif kit == "scale":
    cube("Base", (0, 0, 0.12), (2.2, 0.7, 0.18), BODY)
    cube("Post", (0, 0, 1.15), (0.12, 0.12, 2.0), BRASS)
    beam = cube("Beam", (0, 0, 2.15), (3.2, 0.1, 0.08), BRASS)
    cube("Left pan", (-1.3, 0, 1.55), (0.7, 0.7, 0.06), PAPER)
    cube("Right pan", (1.3, 0, 1.55), (0.7, 0.7, 0.06), PAPER)
    beam.rotation_euler = (0, math.radians(-7), 0)
    beam.keyframe_insert("rotation_euler", frame=1)
    beam.rotation_euler = (0, math.radians(7), 0)
    beam.keyframe_insert("rotation_euler", frame=scene.frame_end)
    look = (0, 0, 1.4)
    start, end = (2.4, -4.8, 2.2), (0.6, -3.2, 1.6)
elif kit == "desk":
    cube("Desk", (0, 0, 0.45), (3.4, 1.6, 0.16), DOOR)
    cube("Folder", (-0.4, 0, 0.7), (1.1, 0.8, 0.22), FOLDER)
    cube("File A", (0.9, 0.2, 0.62), (0.45, 0.6, 0.12), PAPER)
    cube("File B", (1.15, -0.15, 0.74), (0.45, 0.6, 0.12), PAPER)
    look = (0, 0, 0.7)
    start, end = (1.6, -4.6, 2.4), (0.2, -3.0, 1.7)
else:
    cube("Camera body", (-1.6, 0.2, 0.7), (0.46, 0.32, 0.32), BODY)
    cylinder("Lens", (-1.15, 0.2, 0.7), (0.14, 0.14, 0.36), BRASS)
    page = plane("Page", (1.6, 0, 0.65), (1.3, 1.7, 1), PAPER)
    page.rotation_euler = (math.radians(68), 0, 0)
    cube("Folder", (0, -0.2, 0.28), (1.0, 0.75, 0.2), FOLDER)
    look = (0, 0, 0.7)
    start, end = (1.8, -5.0, 2.4), (0.2, -3.2, 1.7)

cube("Backdrop", (look[0], look[1] + 3.2, 1.6), (9, 0.08, 4.2), WALL)


def aim(camera, place, focus, frame):
    camera.location = place
    direction = Vector(focus) - Vector(place)
    camera.rotation_euler = direction.to_track_quat("-Z", "Z").to_euler()
    camera.keyframe_insert("location", frame=frame)
    camera.keyframe_insert("rotation_euler", frame=frame)


bpy.ops.object.camera_add(location=start)
camera = bpy.context.object
scene.camera = camera
camera.data.lens = 35
aim(camera, start, look, 1)
aim(camera, end, look, scene.frame_end)
bpy.context.view_layer.update()

scene.render.filepath = out
scene.render.image_settings.media_type = "VIDEO"
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.audio_codec = "NONE"
bpy.ops.render.render(animation=True)
'''


def choose_kit(scene: dict) -> str:
    """Pick a built-in 3D set from the scene heading, then from the picture prompt."""
    heading = str(scene.get("heading", "")).lower()
    prompt = str(scene.get("image_prompt", "")).lower()
    if "warning" in heading or "synthetic" in heading:
        return "overview"
    for text in (heading, prompt):
        if any(word in text for word in ("ethic", "privacy", "balance", "scale")):
            return "scale"
        if "redact" in text or "statement" in text:
            return "document"
        if any(word in text for word in ("combin", "merg", "synthesis")):
            return "merge"
        if "porch" in text:
            return "porch"
        if any(word in text for word in ("case file", "dashboard", "building", "desk")):
            return "desk"
    return "overview"


def find_blender() -> str | None:
    """The Blender app on this machine, or nothing when it is not installed."""
    env = os.environ.get("BLENDER", "").strip()
    if env and Path(env).is_file():
        return env
    mac = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if mac.is_file():
        return str(mac)
    return shutil.which("blender")


def render_with_blender(binary: str, script_path: Path, out_file: Path, seconds: float, kit: str) -> None:
    """Run Blender in the background. Its own progress stays on the terminal."""
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(BLENDER_SCRIPT, encoding="utf8")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    command = [
        binary,
        "--background",
        "--factory-startup",
        "--python",
        str(script_path),
        "--",
        "--out",
        str(out_file),
        "--seconds",
        f"{seconds:.3f}",
        "--kit",
        kit if kit in KITS else "overview",
        "--fps",
        "12",
    ]
    result = subprocess.run(command, text=True)
    if result.returncode != 0 or not out_file.is_file():
        raise RuntimeError(
            "Blender did not finish the 3D picture. The Blender script is saved at "
            f"{script_path}."
        )
