# PC2 Tribune Builder (beta)

Blender add-on that turns grandstands into working show rides for Planet Coaster 2.
Guests walk in, take a seat, watch the show and leave again – just like at the cinema ride.

* **Generator** – build a tribune from settings: straight, angled, L, U, arcs, arenas, any mix of pieces
  and angles. Rows, row depth and rise, stairs (left, right, middle, at corners or anywhere you like),
  show area, walkways, entrances, railings and the ride booth.
* **Own model** – use any tribune you modelled yourself. The add-on finds the seats, works out where guests
  can walk (navmesh) and makes the ride outline.
* **Seats** – the built-in stadium seat or your own seat model. Random free seats between groups of guests
  make the audience look real.
* **Everything stays editable** – seats, walk targets, navmesh, outline and booth are normal Blender objects.
* **Check** – tests that guests can walk from an entrance to every seat before you export.
* **One click into the game** – every tribune becomes its own mod folder `Mod_TB_<ID>` and is installed.

## Requirements

* Blender 4.2 or newer
* cobra-tools Blender add-on (installed and enabled)
* In the game: ACSE, ForgeUtils and the **Silver Screen DLC** (the tribunes are based on its cinema ride)

## Installation

1. Blender: *Edit > Preferences > Add-ons > Install from Disk*, choose `pc2_tribune_builder.zip`, enable it.
2. In the add-on preferences set the **ovldata folder**
   (`...\steamapps\common\Planet Coaster 2\Win64\ovldata`).
3. If the panel says that packages are missing, press *Install missing packages* and restart Blender.

The panel is in the 3D view sidebar (N), tab **Tribune**. With Blender's interface language set to German
the add-on is shown in German.

## Generator in 5 steps

1. *New: generator*.
2. **Shape** – pick a preset or build the front line from pieces. The rows lie behind the front line,
   the audience looks over it. *Angle* bends a piece; positive angles bend the tribune around the show area.
3. **Rows and seats** – number of rows, depth, rise, height of the first row, seat model.
4. **Stairs** and **Around the tribune** – stairs, show area, walkways, entrances, booth, railings.
5. *Generate tribune*. Change settings and generate again as often as you like.

Then: *Check* → *Save to library* → *Build mod and install*. Close the game while building.

## Own model

1. *New: own model* (selected objects are moved into the tribune). The centre of the ride is the
   world origin, the audience looks to **-Y**.
2. Put a *Stage point* where the audience looks at, select the seat meshes, *Seats from selection*.
   Each loose part (or each object) becomes a seat with a sit point (arrow) and a walk target (sphere).
3. *Outline around model*, *Ride booth at cursor*, *Navmesh from model*.
4. *Check*, fix what it reports, *Save to library*, *Build mod and install*.

## Editing by hand

| Object | What you can change |
| --- | --- |
| Seat (arrow) | Position = where the guest sits, arrow = viewing direction. Row, place and *Free* in the *Seats* panel. |
| Walk target (sphere, child of a seat) | Where the guest walks to before sitting down. Must be on the navmesh. |
| Navmesh (green) | Where guests can walk. Neighbouring triangles must share whole edges. |
| Outline | Footprint of the ride. Edges marked as **seam** are entrances/exits. |
| Ride booth (cube) | Position of the operator booth; must be inside the outline. |

Materials: colour, roughness and metal of the Principled BSDF are used. *Double-sided* is for single
surfaces such as seat shells.

## Tips

* The walking lane in front of the seats needs at least 0.4 m; 0.5 m or more feels better.
* Guests sit turned the wrong way on angled tribunes? Set *Seat rotation* to *Mirrored* in the library
  settings and build again.
* The show length is set in the game with the ride time (30 s to 15 min).

This is a beta. Keep backups of your parks.
