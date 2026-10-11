"""Parametric bracket built with the scripting API.

Run headless:   kerfline --run examples/bracket.py --out bracket.f3x
or in the GUI:  Tools > Run Script...  (the open design is changed and every step shows in the timeline)
"""
design.param("width", "70 mm")
design.param("depth", "40 mm")
design.param("thickness", "6 mm")

# base plate with rounded corners
sk = design.sketch("XY")
sk.rect(0, 0, "width", "depth")
plate = design.extrude(sk.profile(5, 5), "thickness")
design.fillet(plate.edges(direction=(0, 0, 1)), "4 mm")

# upright rib along the back edge
rib_sk = design.sketch("XZ")
rib_sk.line((5, 6), (65, 6))
design.rib(rib_sk.curves(), "5 mm", "30 mm")

# mounting holes, one tapped for an M6 screw
top = design.bodies[0].face(normal=(0, 0, 1), at_z=6)
design.hole(top, at=(12, 20), diameter="6.5 mm", depth="6 mm")
design.hole(top, at=(58, 20), thread="M6x1", depth="6 mm")

# engraved label on the plate
label = design.sketch(design.bodies[0].face(normal=(0, 0, 1), at_z=6))
label.text(20, 5, "F360", 7)
design.extrude(label.profiles()[:4], "-0.6 mm")      # glyph regions; pushing in cuts automatically

print("volume: %.0f mm^3" % design.bodies[0].volume)
