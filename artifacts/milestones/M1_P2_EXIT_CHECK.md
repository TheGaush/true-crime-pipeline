# M1-P2 exit check

Verified offline on this branch with `tools/verify_m1_p2.ps1`.

- Callout centroids for A1 and J10 stay within 1 px.
- A 50 second tour plans exactly 1500 frames and stays at or under zoom 3.8.
- Ten procedural cues are 48 kHz.
- A text-to-video bookend passes safety and writes no PNG.
- Catalog sources contain no `<feTurbulence>` or `<feDisplacementMap>` elements.
- The checker finished in under a second. No provider was called.

TC-Task-ID: 152
TC-Track: Part 2
TC-Never-Merge: true
