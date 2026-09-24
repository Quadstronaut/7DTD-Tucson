# Tucson_AZ — 7 Days to Die custom world + DayZ/Walking Dead mode

Status: **design + spike stage** (2026-09-24). This doc is the handoff: everything learned, decided, and pending.
Ground rule from the user: **never guess game mechanics.** Verify from game files / decompiled code / docs, or ask.

## 1. Goal

A multiplayer (friends) 7DTD world of Tucson, AZ, at the largest in-game size (10240 x 10240), plus a
DayZ x Walking Dead game mode. Accuracy of the map's basic shapes and structure wins over detail.

## 2. Decisions (user)

| Topic | Decision |
|---|---|
| Game version | Installed **V.3.0.259** (not "v1.0" as the Gemini prompt claimed) |
| World size | **10240** (largest in-game option) |
| Scale | Fit Tucson in. Landmarks may be exaggerated; neighborhoods compressed (only need dozens of houses) |
| West wall | **Old Tucson** movie studio |
| Must include | Tucson Mtns, highways, downtown, UA campus, Davis-Monthan AFB, Mt Lemmon, **Skate Country** (user is a quad skater) |
| Tucson Intl Airport | **Only if room** — adjacent civil + military airfields eat lots of empty space |
| Roads | Real roads, accurate shapes. Capture SOME of overpasses, barriers, lanes. World Editor hand pass OK |
| Pipeline | **C**: importer mod (terrain + biomes) → vanilla RWG → World Editor hand pass. **B** (full custom Python) is fallback |
| Headshots | **Headshot Finisher**. Living severed head = future mod idea, not now |
| Mode | Already built by the user via Sandbox Options and working (see §7) |

## 3. Landmarks (OSM / Nominatim, verified)

| Landmark | Lat | Lon |
|---|---|---|
| Old Tucson (theme park way) | 32.2181 | -111.1286 |
| Tucson City Hall | 32.2226 | -110.9748 |
| Hotel Congress | 32.2223 | -110.9667 |
| University of Arizona (relation center) | 32.2289 | -110.9565 |
| Davis-Monthan AFB (relation centers) | 32.1662 / 32.1571 | -110.8819 / -110.8486 |
| D-M ammo depot | 32.1448 | -110.8252 |
| Skate Country, 7980 E 22nd St | 32.2064 | -110.8222 |
| Mt Lemmon peak (ele 2794 m) | 32.4424 | -110.7890 |
| Tucson Intl Airport (optional) | 32.1147 | -110.9358 |

Landmark span ≈ **32 km E-W × 36 km N-S** → uniform scale ≈ 3.6 m/block at 10240.

## 4. Scale design

- **Separable piecewise-linear warp**: independent X(lon) and Z(lat) mappings. Landmark bands ~2:1, filler squeezed.
  Tucson's arterials are a N-S/E-W grid, so a separable warp keeps them straight. Diagonals (I-10) bend slightly at band edges — acceptable.
- Vertical: real 700 m (valley) → 2794 m (Lemmon). Map into block heights; max safe terrain height UNVERIFIED
  (vanilla RWG max seen: 197). Spike tests a candidate.
- Vertical exaggeration will be lower than horizontal compression (mountains gentler than real) — unavoidable.

## 5. Verified file-format facts (from installed game + real generated worlds)

- `dtm.raw`: little-endian uint16, N×N, **block height = value/256**, **row 0 = south** (z = row − N/2).
- `prefabs.xml`: `<decoration type="model" name=".." position="x,y,z" rotation="0-3"/>`, x/z **centered on map middle**.
  Y ≈ terrain height + prefab `YOffset` + 1 (fit on 400/400 placements, both corner and center anchors).
- `biomes.png` (RWG output): RGBA at **1/8 scale**.
- `splat3.png`: RGBA, **R = asphalt, G = gravel** only (blue unused in generated worlds).
- Biome colors (`Data/Config/biomes.xml`): forest `#004000`, burnt `#BA00FF`, desert `#FFE477`, snow `#FFFFFF`, wasteland `#FFA800`.
- `main.ttw` is binary (copy from template; don't author).
- `map_info.xml` V3 includes `HeightMapSize`, `Scale`, `Modes`, `FixedWaterLevel`, `RandomGeneratedWorld`, `GameVersion`.
- Max RWG size in `serverconfig.xml`: 6144–10240, multiples of 2048.

### Gemini prompt errors (do not reuse)
Wrong version; game reads `dtm.raw` not `heightmap.png`; desert/forest colors wrong (`#FFA800` is wasteland);
7/10 prefab names nonexistent (cinema_01, library_01, skatepark_01, army_base_01, airfield_01, hangar_01, theater_01);
lon typo -100.70; prefab coords not corner-origin; main.ttw not XML.

### Real prefabs worth using
`base_military_01`, `army_camp_01..10`, `skyscraper_01..04`, `remnant_skyscraper_01..05`, `downtown_*`,
`aaa_arizona_downtown_01`, `school_01..03`, `hospital_01`, `remnant_library_01/02`, `football_stadium`,
`soccer_stadium_01`, `remnant_sports_center_01` (Skate Country stand-in candidate), `theater_stage_01`,
`prison_01/02`, `police_station_03`, `bunker_00`.
Road structure: `part_highway_overpass`, `part_highway_transition`, `hwy_overpass_sign_01`,
`bridge_concrete_1/2`, `bridge_asphalt1`, `rwg_bridge_tile_01`, `rwg_bridge_end_01`. (Not yet inspected — sizes/usage TBD.)

## 6. Importer mod — facts from decompiled code

Custom Height Map Importer, Nexus mod 9220, v4.1 (2026-09-12), author John Nicholson, **V3.x compatible**.
DLL decompiled with `ilspycmd` (dotnet global tool) → `%TEMP%\chmi\src`.

- Install: folder into `<game>/Mods/`; put `heightmap.png` in the mod folder; generate a new RWG world.
- `heightmap.png`: square, **must equal world size exactly** (10240) else vanilla fallback; 8/16-bit gray/RGB/RGBA, non-interlaced.
  **Height = value / 257** blocks. PNG **top row = north** (decoder flips rows).
- `biomes_source.png`: same size as heightmap; 5 vanilla colors, ±10 tolerance; **unknown color → forest**.
- Water masks optional (`water map.png`, `rivers_mask.png`, …). Tucson rivers are dry → skip.
- RWG still places towns/roads/POIs; city sites chosen from the **flattest ~35%** of candidate tiles (150-block tiles + 20 band, ≤10-block relief preferred).
  → Flatten downtown/campus areas in the heightmap to steer cities there.
- After RWG, restores **exact imported heights** before save (roads/plots don't reshape terrain).
  → Real highways must be carved into our heightmap ourselves.
- Mod only affects generation; output world is ordinary files (per author) → ship world folder to server.

## 7. Game mode (user-built, working)

All map to native V3 **Sandbox Options** (descriptions verified in `Localization.csv`). Server uses `SandboxCode` in `serverconfig.xml`
(copy code from the new-game Sandbox screen). **TODO: user supplies SandboxCode.**

| Want | Option |
|---|---|
| Monthly blood moons | BloodMoonFrequency (days between) |
| Zombies more active by day | ZombieMove (day) > ZombieMoveNight |
| Zombies eat hunted game | ZombiesEatAnimals |
| Headshots required | HeadshotMode = Headshot Finisher |
| Drop bag, keep belt | DropOnDeath = Backpack Only |
| Traders claimable | TraderProtection |
| Quests/milestones on | QuestsEnabled, ChallengesEnabled |
| Weak hits, deadly infection | EntityDamage low, InfectionRate max |
| No map, compass on | AllowMap off, AllowCompass on |

## 8. Pipeline C plan

1. **Spike (now)**: real DEM → 10240 16-bit heightmap + biomes_source → importer mod → generate in V3 → verify orientation, height scale, peak height, load/playability.
2. Scale warp + flattened landmark zones (downtown, UA, DM AFB, Skate Country, Old Tucson).
3. Real roads: rasterize OSM motorway/trunk/primary into the heightmap (graded road bed, barriers as small berms?) — then verify in game
   whether RWG road splat can be replaced/augmented with our asphalt. Overpasses need bridge prefabs (heightmap is single-layer).
4. World Editor hand pass: landmark POIs, overpasses, Skate Country.
5. Package world → friends' dedicated server + SandboxCode.

## 9. Open items / unknowns

- Max safe terrain height (spike).
- Can generated `splat3.png` be edited post-RWG and honored? (`splat3_processed.png` also exists — unknown which the game reads.)
- Bridge/overpass prefab dimensions + whether RWG roads can be suppressed.
- DEM source: USGS 3DEP via OpenTopography (API key?) or AWS terrain tiles (no key). Spike uses whatever works keyless.
- Airport inclusion depends on warp budget.

## 10. Side task: AdNauseam in Playwright MCP browser — DONE 2026-09-24

- Chromium route dead: AdNauseam Chromium build is MV2; Playwright Chromium 149 hangs loading it; branded Chrome ignores `--load-extension`.
- Working route: **stock Firefox via Scoop** (`scoop install extras/firefox`, 156.0.1) driven over WebDriver BiDi (`channel: moz-firefox`).
  Signed AMO XPI (`adnauseam@rednoise.org` 3.28.8) dropped into profile `extensions/`; verified `active: true`.
- Config: `~/.claude/playwright-mcp-firefox.json`; `~/.claude.json` playwright args += `--config <that>` (backup `.claude.json.bak-2026-09-24-adnauseam`).
  Profile persists at `%LOCALAPPDATA%\ms-playwright\mcp-firefox-persistent` (all projects share it). Needs `-wait-for-browser` (Windows launcher process) + `-no-remote`.
- Takes effect on next Claude Code restart. Revert = remove the two `--config` args.

## 11. Spike status

- `tools/spike_heightmap.py` → `out/spike/` (gitignored). Box W-111.14 E-110.717 S32.10 N32.46, 39.8 km square, 3.89 m/block, blocks 35–214.
  Lemmon peak lands at expected pixel (row 498, col 8503) → orientation correct.
- Installed into `<game>/Mods/CustomHeightMapImporter/` with heightmap.png + biomes_source.png.
- **NEXT (user, in game):** New Game → generate RWG world at **10240**, any seed, preview on. Then Claude reads
  `%APPDATA%\7DaysToDie\logs` + the new GeneratedWorlds folder to verify mod ran, heights, orientation.
- Mod is a DLL; if it doesn't load, check whether the game must be launched without EAC (unverified).
- **Remove the mod folder (or its heightmap.png) after the spike** or every future RWG world becomes Tucson.

### Spike result — PASSED 2026-09-24

- User generated **"Tisuviro County"** (10240, seed name "Claude Code"). Map_info GameVersion **V.3.20.10** (game has updated past 3.0.259).
- DLL mod **requires launching without EAC** (verified; log: "Mod contains custom code, AntiCheat needs to be disabled").
- `dtm.raw` vs source: |diff| ≤ 0.87 block everywhere (constant ~-0.8 offset, 256 vs 257 scaling) → import is exact; orientation correct.
- `biomes.png` 1280² (1/8), only our 3 colors; ~99% of 32-block cells uniform → biome detail is fine (log's "40x40 logical cells" is not the output resolution).
- 5794 POI plots rejected for terrain; 1199 POI footprints kept → full build must flatten landmark zones (DM AFB is flat IRL anyway).
- RWG roads/cities are wrong as expected → handled by real-road carving + hand pass.
- Mod removed from game `Mods/` → moved to `vendor/CustomHeightMapImporter/` (gitignored; third-party DLL). Reinstall by copying back when building.
- Spike output world is not saved to repo (lives in `%APPDATA%\7DaysToDie\GeneratedWorlds\Tisuviro County`).

## 12. TODO (non-map)

- [ ] **Make repo public** (`gh repo edit Quadstronaut/7DTD-Tucson --visibility public --accept-visibility-change-consequences`).
      Before flipping: scrub personal paths if unwanted (spec cites `C:\Users\Quadstronaut\...`); never commit vendor/ (third-party DLL).
- [ ] **Bedazzled README.md** (use the `bedazzle` skill; match the user's other repos).
- [ ] **Discord announcement channel** like the others. Mechanism (verified): QuadstroNot bot repo-digest —
      `G:\Documents\GIT\BUSINESS-pursuits\QuadstroNot\config\github_channels.json` maps repo globs → channel names;
      the `/github-channels` project skill (run inside QuadstroNot) diffs config vs Discord and creates the channel via the admin MCP.
      Add `{ "name": "7dtd-tucson", "repos": ["7DTD-Tucson"] }` (channel name = user's call), then run `/github-channels` there.
      QuadstroNot may have its own agents committing — coordinate before editing.

## 13. Build design (proposed 2026-09-24, awaiting approval)

### 13.1 Key verified facts driving the design
- RWG `Towns` and `Wilderness` each accept **None / Few / Default / Many** (`xuiWorldGeneration*` localization; tooltip "Enables or Disables Town Generation").
- A generated `prefabs.xml` lists **everything explicitly**: 150×150 `rwg_tile_*` street tiles, every house/POI inside them, every `part_*`, and traders (Cesetalu: 491 tiles, 2658 parts, 5 traders).
- Street tiles declare their building slots in their XML: `POIMarkerStart/Size/Type/Tags/Group` (e.g. residential_straight: five 42×0×42 POISpawn slots + streetlight PartSpawns with chance 0.2).
- Tile families: commercial, countryresidential, countrytown, downtown, gateway, industrial, **oldwest** (→ Old Tucson!), residential, rural; each has cap/corner/intersection/straight/t.
- Useful POIs: `base_military_01` 100×100 (Industrial), `football_stadium` 100×100 (→ Arizona Stadium @ UA), `remnant_sports_center_01` 100×100 (Skate Country stand-in), `skyscraper_01..04` 60×60, `theater_stage_01`, `bridge_concrete_1` 13×39, `bridge_asphalt1` 15×43. `part_highway_overpass`/`transition` are tagged testonly/part — usable only if they actually render; verify.
- A freshly generated world has **no `*_processed` files** until first load → post-editing `prefabs.xml` / `splat3.png` before first load should be honored (VERIFY in step 5 spike).

### 13.2 Approach: mod for terrain, our code for everything built
RWG (with importer mod) runs with **Towns = None, Wilderness = None** only to produce the engine-owned files
(`dtm.raw`, `main.ttw`, `biomes.png`, `splat4`, `radiation.png`, `map_info.xml`). Our Python then **overwrites
`prefabs.xml`, `splat3.png`, `spawnpoints.xml`** with real Tucson. No reliance on RWG's placement heuristics.
(Fallback B = also write dtm.raw ourselves and drop the mod — only if the mod blocks something.)

### 13.3 Components (one script each, `tools/`)
1. **`warp.py` — separable piecewise-linear scale.** Control points per axis (lon→x, lat→z) put landmark bands at ~2 m/block and
   squeeze filler. Keeps the N-S/E-W arterial grid straight. Single source of truth used by every other step.
   Box: west = Old Tucson (−111.14), east ≈ −110.72, south = 32.10 (Tucson Intl fits at uniform scale; kept only if budget allows), north ≈ 32.46.
2. **`terrain.py` — DEM → heightmap.png + biomes_source.png.** Higher-res DEM (terrarium z14 ≈ 8 m, keyless). Through the warp.
   Flatten landmark footprints (DM AFB, downtown, UA, Skate Country, Old Tucson, airport) to their median height.
   Biomes: desert basin, forest (Catalinas mid), snow (Lemmon summit). Height mapping as spike (valley 35 → peak ~214).
3. **`roads.py` — OSM → graded road beds + splat3.** Classes: motorway/trunk (I-10, I-19), primary/secondary arterials.
   Widths scaled (motorway ≈ 16 blocks incl. shoulders, arterial ≈ 8–10). Road bed = heightmap smoothed along centerline with max grade.
   Paint splat3 R (asphalt). **Overpasses:** raise the interstate as a berm; crossing arterials cut under; place `bridge_concrete_*` over the cut.
   Barriers/lane lines: out of scope v1 (need custom prefab blocks) — revisit after v1 plays.
4. **`neighborhoods.py` — real street grid → street tiles.** In chosen neighborhood zones, snap to the warped arterial grid and lay
   `rwg_tile_*` (downtown near Congress/Broadway, residential/countryresidential in filler, industrial near rail/DM, oldwest at Old Tucson).
   Fill each tile's POISpawn slots with size/zoning-matching POIs. **Slot-fill rule is learned from Cesetalu/Tisuviro prefabs.xml**
   (tile pos + rotation → house pos + rotation), not guessed.
5. **`landmarks.py` — hand-listed placements** (YAML): downtown skyscrapers, UA (+ football_stadium), DM AFB (`base_military_01`,
   army camps, runway = asphalt splat strip on flattened ground), Skate Country, Old Tucson, Mt Lemmon (Summerhaven cabins), traders spread
   across the map. Y from dtm + YOffset + 1 (verified rule).
6. **`assemble.py` — write prefabs.xml / splat3.png / spawnpoints.xml into the generated world; copy to GeneratedWorlds.**

### 13.4 Order & verification (each step ends in-game)
1. Warp + terrain + flattened zones → regenerate (Towns/Wilderness None) → check landmark zones flat and where expected.
2. **Post-edit spike:** hand-add 3 prefabs + one asphalt stripe to that world's prefabs.xml/splat3.png → load → confirm honored.
3. Roads → verify I-10/I-19 shape, grades drivable, one overpass works.
4. Landmarks → walk to each.
5. Neighborhoods (slot-fill rule from data) → verify houses sit in lots, quests work.
6. Airport if space; package for the friends' dedicated server + SandboxCode.

### 13.5 Out of scope v1 (YAGNI)
Lane striping, concrete barriers, water, custom prefabs, the living-severed-head mod, residential streets outside tile zones.

### Plan 1 progress (2026-09-24)
- Tasks 1–3 done (17 tests). Warped terrain built; zones verified in `tucson.overlay` view.
- Task 4 done: regenerated "Tisuviro County" with Towns=None, Wilderness=None → **prefabs.xml empty (`<prefabs />`), no traders, splat3 empty**;
  RWG still wrote 12 spawnpoints (some at y≈185 in the Catalinas). dtm vs heightmap max |diff| 0.87. Mod removed from game again.
- Task 5 applied: 3 POIs at world (0,*,0), (200,*,0), (400,*,0); asphalt stripe at splat3 image rows 4820–4827, cols 5120–5719
  (→ z ≈ +300 if image row 0 = north, z ≈ −300 if row 0 = south). Awaiting in-game report.

### Plan 1 RESULT — PASSED (user in-game, 2026-09-24, game V3.2.0 b10 / map_info V.3.20.10)
- **Post-generation edits to prefabs.xml are honored**; POIs sit on the ground with Y = dtm + YOffset + 1 (verified: sports center, skyscraper, stadium).
- **Post-generation edits to splat3.png are honored** (asphalt stripe rendered as a road).
- **splat3.png image row 0 = NORTH** (stripe at rows 4820–4827 appeared north of z=0). Same orientation as heightmap.png; opposite of dtm.raw (row 0 = south).
- First load creates `dtm_processed.raw`, `splat3_processed.png`, `splat3_half.png`, `splat4_processed.png`, `splat4_half.png`, `checksums.txt`.
  → Author edits into a **never-loaded** world copy. Whether deleting the derived files forces a rebuild is UNVERIFIED.
- Test save for this world should be deleted before real play (it has chunks generated from the test edits).

### Plan 2 progress (2026-09-24)
- **Hand-assembled world loads** (user in game): game builds its `*_processed` files itself from our dtm.raw/splat3.png — no mod/EAC loop needed anymore.
  Debug map shows "VERY familiar roads".
- User change: whole Mt Lemmon drive must be on-map (ski resort later). Box widened: **E −110.66, N 32.47**; warp rebalanced
  (x: [0,0],[3,1100],[14,3000],[19.5,5000],[21.5,5350],[31.5,7700],[45.18,10240]; z: …,[36,8900],[40.91,10240]).
  Verified: Catalina Hwy / General Hitchcock Hwy from Tanque Verde to Summerhaven fully inside.
- `biomes.png` now written by us: RGBA, **1/8 scale, row 0 = north, alpha 255** (verified 99.9% match vs RWG output).
- Assemble clears stale derived files in the target world. Existing saves of a rebuilt world must be deleted (chunks cached).
- Ski Run Road's upper part is `highway=unclassified` (not in road classes) → add explicitly with the ski resort (Plan 3).
- Height curve (user-approved "option 2 @ 235"): piecewise [[650,35],[1000,48],[2800,235]] replaces linear 650→35 / 2800→215.
  Built: summit 233.7, Ski Valley 208.8, Summerhaven 190.4, downtown 37.8, world median 41.3. Safe ceiling for POIs at the
  summit still UNVERIFIED (check with the ski lodge in Plan 3).
