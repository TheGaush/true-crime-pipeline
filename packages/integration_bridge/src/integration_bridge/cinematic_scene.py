"""Blender entry for one cinematic documentary scene. Run this file with Blender, not Python."""

import math
import sys

try:
    import bpy
    from mathutils import Matrix, Vector
except ImportError:
    raise SystemExit("This file runs inside Blender.")

argv = sys.argv[sys.argv.index("--") + 1 :]


def flag(name, default):
    if name not in argv:
        return default
    return argv[argv.index(name) + 1]


out = flag("--out", "")
seconds = float(flag("--seconds", "4"))
kit = flag("--kit", "overview")
fps = int(flag("--fps", "30"))
samples = int(flag("--samples", "24"))
width = int(flag("--width", "1920"))
height = int(flag("--height", "1080"))
frame_flag = flag("--frame", "")
heading = " ".join(
    "".join(character if character.isalnum() or character == " " else " " for character in flag("--heading", "Scene")).split()
)[:28] or "Scene"
if kit not in ("overview", "porch", "document", "merge", "desk", "scale"):
    kit = "overview"

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = max(fps * 2, int(round(seconds * fps)))
scene.render.fps = fps
scene.render.resolution_x = width
scene.render.resolution_y = height
scene.render.resolution_percentage = 100
scene.render.use_motion_blur = False
engine = None
for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        scene.render.engine = candidate
        engine = candidate
        break
    except TypeError:
        continue
if engine is None:
    raise RuntimeError("This Blender has no Eevee engine.")
eevee = scene.eevee
eevee.taa_render_samples = samples
if hasattr(eevee, "taa_samples"):
    eevee.taa_samples = min(16, samples)
if hasattr(eevee, "use_raytracing"):
    eevee.use_raytracing = False
if hasattr(eevee, "use_gtao"):
    eevee.use_gtao = True
try:
    scene.view_settings.view_transform = "AgX"
except TypeError:
    scene.view_settings.view_transform = "Filmic"
scene.view_settings.exposure = -0.55
try:
    scene.view_settings.look = "AgX - Medium Contrast"
except TypeError:
    pass

world = bpy.data.worlds.new("Storm")
scene.world = world
world.use_nodes = True
background = world.node_tree.nodes["Background"]
sky = world.node_tree.nodes.new("ShaderNodeTexSky")
try:
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(36)
    sky.sun_rotation = math.radians(50)
    sky.air_density = 1.0
    sky.dust_density = 1.6
    sky.ozone_density = 1.0
    sky.sun_intensity = 0.28
    sky.sun_disc = False
except AttributeError:
    pass
world.node_tree.links.new(sky.outputs["Color"], background.inputs["Color"])
background.inputs["Strength"].default_value = 0.55


def set_input(node, names, value):
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return


def material(name, color, rough=0.55, metal=0.0, emission=0.0, bump=0.0, scale=6.0, variation=0.0, coat=0.0):
    """A surface with grain. variation and bump keep a wall from reading as flat paint."""
    made = bpy.data.materials.new(name)
    made.use_nodes = True
    tree = made.node_tree
    node = tree.nodes["Principled BSDF"]
    set_input(node, ("Base Color",), (*color, 1))
    set_input(node, ("Roughness",), rough)
    set_input(node, ("Metallic",), metal)
    set_input(node, ("Specular IOR Level", "Specular"), 0.4)
    set_input(node, ("Coat Weight",), coat)
    set_input(node, ("Emission Color", "Emission"), (*color, 1))
    set_input(node, ("Emission Strength",), emission)
    if bump <= 0 and variation <= 0:
        return made
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.55
    if bump > 0:
        bump_node = tree.nodes.new("ShaderNodeBump")
        bump_node.inputs["Strength"].default_value = bump
        bump_node.inputs["Distance"].default_value = 0.015
        tree.links.new(noise.outputs["Fac"], bump_node.inputs["Height"])
        tree.links.new(bump_node.outputs["Normal"], node.inputs["Normal"])
    if variation > 0:
        mix = tree.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        darker = tuple(max(0.0, channel * (1.0 - variation)) for channel in color)
        mix.inputs["A"].default_value = (*color, 1)
        mix.inputs["B"].default_value = (*darker, 1)
        tree.links.new(noise.outputs["Fac"], mix.inputs["Factor"])
        tree.links.new(mix.outputs["Result"], node.inputs["Base Color"])
        spread = tree.nodes.new("ShaderNodeMapRange")
        spread.inputs["From Min"].default_value = 0.15
        spread.inputs["From Max"].default_value = 0.85
        spread.inputs["To Min"].default_value = max(0.03, rough * 0.7)
        spread.inputs["To Max"].default_value = min(1.0, rough * 1.2)
        tree.links.new(noise.outputs["Fac"], spread.inputs["Value"])
        tree.links.new(spread.outputs["Result"], node.inputs["Roughness"])
    return made


INK = material("Ink", (0.02, 0.02, 0.022), 0.4)
WHITE = material("Title", (0.95, 0.95, 0.93), 0.4, emission=3.0)
BONE = material("Bone", (0.72, 0.64, 0.46), 0.45)
PAPER = material("Paper", (0.86, 0.83, 0.75), 0.78, bump=0.03, scale=40, variation=0.05)
MANILA = material("Manila", (0.62, 0.46, 0.22), 0.7, bump=0.06, scale=12, variation=0.1)
WOOD = material("Wood", (0.40, 0.26, 0.14), 0.52, bump=0.08, scale=14, variation=0.16)
WALL = material("Siding", (0.62, 0.60, 0.57), 0.78, bump=0.06, scale=22, variation=0.07)
TRIM = material("Trim", (0.32, 0.31, 0.29), 0.48, bump=0.02, scale=18, variation=0.04)
DOOR = material("Door", (0.28, 0.15, 0.08), 0.46, bump=0.07, scale=16, variation=0.12)
METAL = material("Metal", (0.22, 0.22, 0.23), 0.32, metal=1.0, bump=0.04, scale=18, variation=0.08)
BRASS = material("Brass", (0.58, 0.42, 0.16), 0.28, metal=1.0, coat=0.15)
WINDOW = material("Window", (0.16, 0.19, 0.21), 0.06, coat=0.35)
GLASS = material("Glass", (0.55, 0.62, 0.64), 0.08, coat=0.2)
CLOTH = material("Cloth", (0.16, 0.17, 0.19), 0.88, bump=0.04, scale=20, variation=0.06)
ROOM = material("Room", (0.24, 0.23, 0.22), 0.84, bump=0.03, scale=8, variation=0.05)
GROUND = material("Concrete", (0.45, 0.44, 0.42), 0.88, bump=0.06, scale=6, variation=0.06)
WARM = material("Lamp", (1.0, 0.78, 0.48), 0.35, emission=12.0)
ROOF = material("Roof", (0.12, 0.12, 0.13), 0.88, bump=0.08, scale=10, variation=0.08)


def mesh(kind, name, location, size, surface, rotation=(0.0, 0.0, 0.0), bevel=0.012):
    if kind == "box":
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    elif kind == "cyl":
        bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=0.5, depth=1, location=location)
    elif kind == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.5, location=location)
    elif kind == "roof":
        bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1, depth=1, location=location)
    else:
        bpy.ops.mesh.primitive_plane_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    obj.rotation_euler = rotation
    if bevel and kind != "plane":
        modifier = obj.modifiers.new("Bevel", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        modifier.limit_method = "ANGLE"
        modifier.angle_limit = math.radians(40)
    obj.data.materials.append(surface)
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    except (AttributeError, TypeError, RuntimeError):
        bpy.ops.object.shade_smooth()
    return obj


def light(kind, name, location, energy, color, size=1.2, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.object.light_add(type=kind, location=location, rotation=rotation)
    lamp = bpy.context.object
    lamp.name = name
    lamp.data.energy = energy
    lamp.data.color = color
    lamp.data.use_shadow = True
    if kind == "AREA":
        lamp.data.size = size
        if hasattr(lamp.data, "size_y"):
            lamp.data.size_y = size
    if kind == "SUN" and hasattr(lamp.data, "angle"):
        lamp.data.angle = math.radians(11)
    return lamp


def adopt(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def caption(text, location, size=0.12, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.object.text_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.004
    obj.data.bevel_depth = 0.001
    obj.data.resolution_u = 6
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            obj.data.font = bpy.data.fonts.load(candidate)
            break
        except RuntimeError:
            continue
    obj.data.materials.append(INK)
    return obj


def figure(name, location):
    root = bpy.data.objects.new(name, None)
    scene.collection.objects.link(root)
    root.location = location
    parts = (
        ("torso", "box", (0, 0, 1.18), (0.38, 0.2, 0.52), CLOTH, 0.02),
        ("hips", "box", (0, 0, 0.86), (0.34, 0.18, 0.22), CLOTH, 0.015),
        ("head", "sphere", (0, 0, 1.62), (0.22, 0.2, 0.26), CLOTH, 0.0),
        ("leg-l", "box", (-0.1, 0, 0.42), (0.12, 0.12, 0.84), CLOTH, 0.01),
        ("leg-r", "box", (0.1, 0, 0.42), (0.12, 0.12, 0.84), CLOTH, 0.01),
        ("arm-l", "box", (-0.28, 0, 1.16), (0.1, 0.1, 0.48), CLOTH, 0.01),
        ("arm-r", "box", (0.28, 0, 1.16), (0.1, 0.1, 0.48), CLOTH, 0.01),
    )
    for label, kind, loc, size, surface, bevel in parts:
        part = mesh(kind, f"{name}-{label}", (0, 0, 0), size, surface, bevel=bevel)
        part.parent = root
        part.matrix_parent_inverse = Matrix.Identity(4)
        part.location = loc
    return root


def page(name, location, rotation, bars=3):
    sheet = mesh("box", name, location, (0.92, 1.22, 0.012), PAPER, rotation, bevel=0.004)
    bpy.context.view_layer.objects.active = sheet
    sheet.select_set(True)
    bpy.ops.object.transform_apply(scale=True)
    for index in range(bars):
        bar = mesh("box", f"{name}-bar-{index}", (0, 0, 0), (0.62, 0.045, 0.008), INK, bevel=0.0)
        bpy.context.view_layer.objects.active = bar
        bar.select_set(True)
        bpy.ops.object.transform_apply(scale=True)
        bar.parent = sheet
        bar.matrix_parent_inverse = Matrix.Identity(4)
        bar.location = (0.0, 0.28 - index * 0.24, -0.02)
        bar.rotation_euler = (0.0, 0.0, 0.0)
        bar.scale = (0.05, 1.0, 1.0)
        bar.keyframe_insert("scale", frame=1)
        bar.scale = (1.0, 1.0, 1.0)
        bar.keyframe_insert("scale", frame=max(8, int(scene.frame_end * 0.45)))
    return sheet


def camera_prop(location, rotation=(math.radians(90), 0, math.radians(180))):
    body = mesh("box", "Camera body", location, (0.22, 0.16, 0.16), METAL, bevel=0.012)
    lens = mesh(
        "cyl",
        "Lens",
        (location[0], location[1] - 0.12, location[2]),
        (0.09, 0.09, 0.16),
        BRASS,
        (math.radians(90), 0, 0),
        bevel=0.004,
    )
    glass = mesh(
        "cyl",
        "Lens glass",
        (location[0], location[1] - 0.2, location[2]),
        (0.07, 0.07, 0.02),
        GLASS,
        (math.radians(90), 0, 0),
        bevel=0.0,
    )
    return body, lens, glass


def folder(location):
    body = mesh("box", "Folder", location, (1.05, 0.78, 0.08), MANILA, bevel=0.008)
    tab = mesh(
        "box",
        "Folder tab",
        (location[0] - 0.22, location[1] + 0.28, location[2] + 0.05),
        (0.34, 0.16, 0.03),
        MANILA,
        bevel=0.004,
    )
    caption("CASE FILE", (location[0], location[1] - 0.02, location[2] + 0.06), 0.08)
    return body, tab


def ease_all():
    for obj in bpy.data.objects:
        data = obj.animation_data
        action = data.action if data else None
        if action is None:
            continue
        curves = list(getattr(action, "fcurves", []) or [])
        if not curves:
            try:
                bag = action.layers[0].strips[0].channelbag(data.action_slot)
                curves = list(bag.fcurves)
            except (AttributeError, IndexError, TypeError):
                curves = []
        for curve in curves:
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"
                point.handle_left_type = "AUTO_CLAMPED"
                point.handle_right_type = "AUTO_CLAMPED"


def track(camera, focus):
    """Keep the horizon level while the camera moves. Euler keys roll in the middle."""
    target = bpy.data.objects.new("Focus", None)
    scene.collection.objects.link(target)
    target.location = focus
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"


def move(camera, place, frame):
    camera.location = place
    camera.keyframe_insert("location", frame=frame)


# Shared ground. Each kit adds its own set, lights, and camera path.
mesh("plane", "Ground", (0, 0, 0), (80, 80, 1), GROUND, bevel=0.0)

look = (0.0, 0.0, 1.0)
start = (2.4, -6.2, 2.2)
end = (0.6, -4.0, 1.6)
lens_mm = 40
fstop = 8.0

if kit == "porch":
    mesh("box", "House", (0, 1.15, 1.55), (6.4, 4.2, 3.1), WALL, bevel=0.02)
    mesh("roof", "Roof", (0, 1.15, 3.55), (3.7, 2.5, 1.35), ROOF, (0, 0, math.radians(45)), bevel=0.015)
    mesh("box", "Porch", (0, -1.85, 0.1), (6.6, 2.3, 0.18), WOOD, bevel=0.008)
    mesh("box", "Step", (0, -3.15, 0.05), (2.2, 0.42, 0.1), WOOD, bevel=0.006)
    mesh("box", "Door", (-0.15, -0.98, 1.15), (1.05, 0.08, 2.15), DOOR, bevel=0.008)
    mesh("cyl", "Knob", (0.22, -1.04, 1.05), (0.06, 0.06, 0.04), BRASS, (math.radians(90), 0, 0), bevel=0.0)
    for side in (-1.7, 1.55):
        mesh("box", f"Window {side}", (side, -0.98, 1.85), (1.15, 0.06, 1.15), TRIM, bevel=0.008)
        mesh("box", f"Pane {side}", (side, -1.02, 1.85), (0.92, 0.02, 0.92), WINDOW, bevel=0.0)
    mesh("box", "Soffit", (2.35, -1.15, 2.55), (0.16, 0.7, 0.08), TRIM, bevel=0.004)
    camera_prop((2.35, -1.35, 2.35))
    mesh("sphere", "Porch bulb", (-2.4, -1.7, 2.55), (0.12, 0.12, 0.12), WARM, bevel=0.0)
    figure("Resident", (-1.55, -1.9, 0.2))
    day = light("SUN", "Day", (8, -10, 9), 6.0, (1.0, 0.95, 0.86))
    day.rotation_euler = (Vector((-2.2, 4.5, -6.0))).to_track_quat("-Z", "Z").to_euler()
    light("AREA", "Sky", (-3, -8, 6), 8, (0.72, 0.8, 0.95), 4.0, (math.radians(-35), math.radians(-20), 0))
    light("AREA", "Porch bulb", (-2.3, -2.0, 2.45), 25, (1.0, 0.62, 0.32), 0.22, (math.radians(-80), 0, 0))
    look = (0.1, -1.1, 1.45)
    start, end = (4.6, -9.4, 1.65), (2.2, -6.4, 1.5)
    lens_mm = 35
    fstop = 11.0
elif kit == "document":
    mesh("box", "Desk", (0, 0, 0.74), (2.4, 1.15, 0.08), WOOD, bevel=0.006)
    for x in (-1.0, 1.0):
        mesh("box", f"Leg {x}", (x, 0.35, 0.36), (0.08, 0.08, 0.72), WOOD, bevel=0.004)
    page("Statement", (-0.12, 0.22, 1.18), (math.radians(68), 0, 0), bars=0)
    for index, height in enumerate((1.48, 1.3, 1.12)):
        mesh(
            "box",
            f"Redaction {index}",
            (-0.12, 0.1, height),
            (0.58, 0.012, 0.045),
            INK,
            (math.radians(68), 0, 0),
            bevel=0.0,
        )
    bpy.ops.mesh.primitive_torus_add(major_radius=0.16, minor_radius=0.018, location=(0.55, -0.22, 0.9))
    ring = bpy.context.object
    ring.rotation_euler = (math.radians(72), 0, math.radians(16))
    ring.data.materials.append(BRASS)
    mesh("cyl", "Handle", (0.78, -0.02, 0.72), (0.03, 0.03, 0.32), METAL, (math.radians(72), 0, math.radians(16)), 0.0)
    mesh("cyl", "Lens disk", (0.55, -0.22, 0.91), (0.26, 0.26, 0.012), GLASS, (math.radians(72), 0, math.radians(16)), 0.0)
    mesh("cyl", "Lamp base", (0.95, 0.35, 0.8), (0.16, 0.16, 0.04), METAL, bevel=0.004)
    mesh("cyl", "Lamp stem", (0.95, 0.35, 1.15), (0.025, 0.025, 0.55), METAL, bevel=0.0)
    mesh("roof", "Shade", (0.95, 0.28, 1.48), (0.28, 0.28, 0.22), METAL, (math.radians(180), 0, 0), bevel=0.004)
    mesh("sphere", "Bulb", (0.95, 0.28, 1.38), (0.08, 0.08, 0.08), WARM, bevel=0.0)
    mesh("box", "Back wall", (0, 1.6, 1.6), (6.5, 0.12, 3.4), ROOM, bevel=0.0)
    light("AREA", "Desk lamp", (0.95, 0.15, 1.35), 90, (1.0, 0.75, 0.48), 0.45, (math.radians(70), 0, math.radians(-20)))
    light("AREA", "Fill", (-1.4, -1.2, 1.8), 12, (0.6, 0.7, 0.85), 1.2)
    look = (0.05, 0.05, 0.95)
    start, end = (1.7, -2.9, 1.9), (0.55, -2.2, 1.55)
    lens_mm = 50
    fstop = 4.0
elif kit == "merge":
    mesh("box", "Table", (0, 0, 0.72), (3.4, 1.4, 0.08), WOOD, bevel=0.008)
    camera_prop((-1.15, -0.05, 0.95))
    page("Record", (1.15, 0.05, 0.95), (math.radians(-68), 0, math.radians(-8)))
    body, _tab = folder((0, 0.05, 0.82))
    body.location = (0, 0.05, 0.7)
    body.keyframe_insert("location", frame=1)
    body.location = (0, 0.05, 0.95)
    body.keyframe_insert("location", frame=scene.frame_end)
    mesh("box", "Back wall", (0, 1.8, 1.5), (7, 0.1, 3.2), ROOM, bevel=0.0)
    light("AREA", "Key", (-1.5, -1.6, 2.4), 140, (1.0, 0.86, 0.7), 1.6, (math.radians(-55), 0, math.radians(-15)))
    light("AREA", "Rim", (2.2, 1.2, 2.2), 30, (0.45, 0.58, 0.8), 1.4)
    look = (0.1, 0.0, 0.9)
    start, end = (0.2, -3.6, 2.5), (0.15, -2.3, 1.7)
    lens_mm = 40
elif kit == "desk":
    mesh("box", "Desk", (0, 0, 0.74), (3.2, 1.25, 0.08), WOOD, bevel=0.008)
    mesh("box", "Wall", (0, 1.3, 1.7), (6.4, 0.1, 3.4), ROOM, bevel=0.0)
    board = mesh("box", "Board", (0, 1.18, 1.85), (2.4, 0.04, 1.5), TRIM, bevel=0.006)
    mesh("box", "Pin A", (-0.45, 1.14, 2.15), (0.55, 0.01, 0.7), PAPER, bevel=0.002)
    mesh("box", "Pin B", (0.4, 1.14, 1.85), (0.55, 0.01, 0.55), PAPER, bevel=0.002)
    folder(( -0.85, -0.05, 0.86))
    page("Note", (0.55, 0.02, 0.86), (math.radians(-70), 0, math.radians(6)), bars=2)
    mesh("box", "Screen", (1.15, 0.15, 1.15), (0.7, 0.04, 0.46), GLASS, (math.radians(-8), 0, 0), bevel=0.004)
    light("AREA", "Desk key", (0, -0.8, 2.2), 120, (1.0, 0.84, 0.68), 1.8, (math.radians(-60), 0, 0))
    light("AREA", "Board wash", (0, 0.2, 2.6), 25, (0.7, 0.78, 0.9), 1.2)
    look = (0.0, 0.3, 1.15)
    start, end = (2.6, -3.4, 1.9), (0.4, -2.5, 1.45)
    lens_mm = 35
elif kit == "scale":
    mesh("box", "Studio wall", (0, 2.2, 1.8), (8, 0.1, 4), ROOM, bevel=0.0)
    mesh("box", "Plinth", (0, 0, 0.18), (1.6, 0.7, 0.28), TRIM, bevel=0.01)
    mesh("cyl", "Post", (0, 0, 1.15), (0.06, 0.06, 1.7), BRASS, bevel=0.0)
    rig = bpy.data.objects.new("ScaleRig", None)
    scene.collection.objects.link(rig)
    rig.location = (0, 0, 1.95)
    beam = mesh("box", "Beam", (0, 0, 1.95), (2.6, 0.08, 0.06), BRASS, bevel=0.004)
    left = mesh("box", "Accuracy pan", (-1.05, 0, 1.55), (0.85, 0.42, 0.04), PAPER, bevel=0.006)
    right = mesh("box", "Privacy pan", (1.05, 0, 1.55), (0.85, 0.42, 0.04), PAPER, bevel=0.006)
    left_label = caption("ACCURACY", (-1.05, -0.2, 1.58), 0.11, (math.radians(78), 0, 0))
    right_label = caption("PRIVACY", (1.05, -0.2, 1.58), 0.11, (math.radians(78), 0, 0))
    for part in (beam, left, right, left_label, right_label):
        adopt(part, rig)
    rig.rotation_euler = (0, math.radians(-8), 0)
    rig.keyframe_insert("rotation_euler", frame=1)
    rig.rotation_euler = (0, math.radians(8), 0)
    rig.keyframe_insert("rotation_euler", frame=scene.frame_end)
    light("AREA", "Overhead", (0, -1.2, 3.4), 80, (1.0, 0.94, 0.86), 3.2, (math.radians(-28), 0, 0))
    light("AREA", "Edge", (-2.4, -1.6, 2.0), 40, (0.55, 0.66, 0.9), 1.4)
    look = (0, 0, 1.45)
    start, end = (3.4, -5.6, 2.35), (0.8, -4.2, 1.9)
    lens_mm = 50
    fstop = 5.6
else:
    mesh("box", "Table", (0, 0, 0.72), (3.6, 1.5, 0.08), WOOD, bevel=0.008)
    mesh("box", "Wall", (0, 1.7, 1.6), (7.2, 0.1, 3.4), ROOM, bevel=0.0)
    camera_prop((-1.2, 0.05, 0.98))
    page("Exhibit", (1.15, 0.0, 0.95), (math.radians(-66), 0, math.radians(6)))
    folder((-0.05, 0.05, 0.84))
    card = mesh("box", "Disclosure card", (-1.15, 0.45, 1.15), (0.7, 0.02, 0.28), PAPER, bevel=0.004)
    caption("SYNTHETIC", (-1.15, 0.42, 1.12), 0.07)
    light("AREA", "Key", (-1.8, -1.8, 2.6), 150, (1.0, 0.86, 0.7), 1.8, (math.radians(-58), 0, math.radians(-12)))
    light("AREA", "Rim", (2.4, 1.0, 2.4), 35, (0.45, 0.6, 0.85), 1.6)
    look = (0.0, 0.05, 0.95)
    start, end = (2.2, -4.4, 2.3), (0.35, -2.8, 1.55)
    lens_mm = 40

bpy.ops.object.camera_add(location=start)
camera = bpy.context.object
scene.camera = camera
camera.data.sensor_width = 36.0
camera.data.lens = lens_mm
camera.data.clip_start = 0.05
camera.data.clip_end = 200
camera.data.dof.use_dof = True
focus = math.dist(end, look)
camera.data.dof.focus_distance = max(0.6, focus)
camera.data.dof.aperture_fstop = fstop
if hasattr(camera.data.dof, "aperture_blades"):
    camera.data.dof.aperture_blades = 6
track(camera, look)
move(camera, start, 1)
move(camera, end, scene.frame_end)
ease_all()
title = caption(heading, (0, 0, 0), 0.2)
title.data.materials.clear()
title.data.materials.append(WHITE)
title.parent = camera
title.matrix_parent_inverse = Matrix.Identity(4)
title.location = (0.0, 0.48, -2.35)
title.rotation_euler = (0.0, 0.0, 0.0)
rule = mesh("box", "Title rule", (0, 0, 0), (0.72, 0.012, 0.004), BONE, bevel=0.0)
rule.parent = camera
rule.matrix_parent_inverse = Matrix.Identity(4)
rule.location = (0.0, 0.34, -2.35)
note = caption("ILLUSTRATIVE", (0, 0, 0), 0.045)
note.data.materials.clear()
note.data.materials.append(WHITE)
note.parent = camera
note.matrix_parent_inverse = Matrix.Identity(4)
note.location = (-0.72, -0.62, -2.35)
bpy.context.view_layer.update()

scene.render.filepath = out
if frame_flag or out.lower().endswith(".png"):
    chosen = int(frame_flag) if frame_flag else max(1, int(scene.frame_end * 0.72))
    scene.frame_set(min(scene.frame_end, max(1, chosen)))
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
else:
    try:
        scene.render.image_settings.media_type = "VIDEO"
    except (AttributeError, TypeError):
        pass
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.audio_codec = "NONE"
    bpy.ops.render.render(animation=True)
