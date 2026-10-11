"""Physical material densities (g/cm^3)."""
MATERIALS = {"Steel": 7.85, "Stainless Steel": 8.0, "Aluminum 6061": 2.70, "Titanium": 4.43, "Copper": 8.96,
             "Brass": 8.5, "ABS Plastic": 1.04, "PLA Plastic": 1.24, "Nylon": 1.15, "Wood (Oak)": 0.75,
             "Glass": 2.5, "Concrete": 2.4}

# surface finish used when shading a body of that material: (specular strength, shininess exponent)
FINISH = {"Steel": (0.55, 90.0), "Stainless Steel": (0.75, 140.0), "Aluminum 6061": (0.5, 60.0),
          "Titanium": (0.45, 50.0), "Copper": (0.6, 70.0), "Brass": (0.65, 80.0), "ABS Plastic": (0.2, 24.0),
          "PLA Plastic": (0.3, 30.0), "Nylon": (0.15, 16.0), "Wood (Oak)": (0.06, 8.0), "Glass": (0.9, 200.0),
          "Concrete": (0.02, 4.0)}
DEFAULT_FINISH = (0.28, 48.0)
