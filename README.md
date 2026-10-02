🎬 Open Mocap — AI-Powered Motion Capture for Blender

Open Mocap is an open-source Blender add-on for AI-powered motion capture.
It supports offline full-body pose tracking, offline + real-time hand tracking, and retargeting to any rig.

---

⚠️ Blender & Dependency Compatibility

Verified combination, exercised headless (see [Tests](#tests)):

| Component | Version |
| --- | --- |
| Blender | 5.2.1 LTS (embeds Python 3.13.15) |
| MediaPipe | 1.0.1 |
| CVZone | 2.0.0 (patched, see `nix/cvzone.patch`) |
| OpenCV | 4.13.0 (nixpkgs) |
| NumPy | 2.5.2 |

Earlier releases targeted Blender 4.0 with MediaPipe 0.10.14, CVZone 1.6.1 and
OpenCV 4.11. Those versions do not work with this Blender: MediaPipe 0.10.14
publishes no wheel for Python 3.13, and CVZone 1.6.1 calls the MediaPipe
`solutions` API that MediaPipe 1.x removed. The pinned versions here replace
both. Blender builds embedding a Python other than 3.13 are refused at Nix
evaluation time rather than failing at import.

The MediaPipe pose and hand models are fetched into the Nix store, so tracking
works offline and never writes into Blender's launch directory. Outside Nix,
set `CVZONE_MODEL_DIR` to a directory containing `pose_landmarker.task` and
`hand_landmarker.task`; with it unset, CVZone downloads them into its working
directory on first use. The store-resident model lookup is a patch to CVZone,
so a non-Nix setup needs the patched package too — see
[Installation without Nix](#installation-without-nix).

> **Preview windows:** the packaged OpenCV is built without a GUI backend, so the
> optional OpenCV preview windows are unavailable and tracking runs without them.
> Real-time tracking is displayed on a plane inside the Blender viewport instead,
> which is unaffected.

---

🚀 Features

✔️ Offline full-body motion capture

Video of the actor below belongs to: https://www.youtube.com/@endlessreference

![PoseTracking GIF](assets/PoseTracking.gif)

✔️ Easy Retargeting of captured motion data to any 3D character

3D character used in video below:
“The Amazing Spiderman” (https://skfb.ly/6sRDt) by iqbalmulyawan is licensed under CC BY 4.0.

![AnimRetargeting GIF](assets/PoseAnimRetarget.gif)

✔️ Offline hand tracking

Video created by Larenju Rai (https://github.com/Larenju-Rai).

![HandTracking GIF](assets/HandTracking.gif)

✔️ Realtime hand tracking

Video created by Larenju Rai (https://github.com/Larenju-Rai).

![RT_HandTracking GIF](assets/RealTimeHandTracking.gif)

🚀 Other Features:

✔️ Blender-native workflow
✔️ Works fully offline

---

## About the Nix packaging in this fork

This repository is upstream's add-on plus a personal Nix layer that exists for one
purpose: a development shell in which the add-on can be built and loaded into a
Blender. It is not a reusable library, and its Nix attributes are not an API.
Another project that needs this add-on should build the add-on and its dependency
environment itself rather than depending on anything here.

This fork uses classic Nix with [npins](https://github.com/nix-community/npins);
there is no flake.

```sh
# Build the add-on.
nix-build release.nix -A open-mocap-blender

# Or enter the development shell.
nix-shell
```

The development shell exports `PYTHONPATH` for the MediaPipe/CVZone/OpenCV
environment and sets `CVZONE_MODEL_DIR` to the store-resident models, so plain
`blender` inside the shell runs with the dependencies importable. The shell also
symlinks the built add-on into your user extensions directory, because Blender
only discovers extensions under a repository name and writes a cache beside them:

```sh
nix-shell
blender
```

Then enable Open Mocap once under Edit ▸ Preferences ▸ Add-ons; it stays enabled
for later launches.

---

## Tests

`tests/smoke.py` runs the add-on in `blender --background` against synthetic
landmark data and a synthetic stick-figure video. It checks dependency imports,
animation, motion combining, pose-capture and hand-routing behaviour,
model-directory handling, baking (all bones, a selected subset, zero selection, a
non-active rig, invalid frame ranges) and unregistration.

Nothing in this fork wraps or runs it. To run it inside the development shell:

```sh
nix-shell
blender --background --factory-startup --python-exit-code 1 --python tests/smoke.py
```

`--python-exit-code` matters: Blender exits 0 after an unhandled exception without
it, so a broken check would look like a pass. Two limits worth knowing:

- It cannot run inside a Nix build sandbox. The MediaPipe wheel bundles tcmalloc,
  whose `CHECK in NumCPUs` aborts when `/sys/devices/system/cpu` is not visible,
  and the sandbox does not expose it. Anyone re-deriving a wrapper around this
  test needs `doCheck = false` for the same reason.
- **Tracking quality is not verified.** Landmark data is fabricated and the
  synthetic video is a stick figure, which MediaPipe does not detect as a person.
  Whether detection produces usable motion from real footage is untested and needs
  a manual pass with a recorded clip. Everything the smoke test asserts about
  capture is that frames reach the detector and are stored, not that the
  landmarks are correct.

---

## Installation without Nix

Install the directory as a Blender extension (Blender ▸ Edit ▸ Preferences ▸
Add-ons ▸ Install from Disk, selecting a zip of this directory). The add-on now
requires Blender 5 or newer; `blender_manifest.toml` is what Blender 4.2+ reads.

Dependencies must already be importable in Blender's Python. The add-on reports
their state under Edit ▸ Preferences ▸ Add-ons ▸ Open Mocap and no longer
installs them, because Blender's bundled Python is replaced on every Blender
upgrade. Point Blender at an environment containing them instead.

The required versions are MediaPipe 1.0.1, CVZone 2.0.0 **with the patch in
`nix/cvzone.patch` applied**, and OpenCV. The patch matters: unpatched CVZone 2.0.0
downloads its models into the working directory on first use and reports every
hand's type as `"Unknown"`, which sends both hands to the same list.

```sh
PYTHONPATH=/path/to/site-packages \
CVZONE_MODEL_DIR=/path/to/models \
blender
```

`CVZONE_MODEL_DIR` must contain `pose_landmarker.task` and `hand_landmarker.task`.
With it set, a missing model is an error rather than a download attempt; with it
unset, CVZone falls back to downloading into its working directory.

---

## Recorded-motion limitations

Behaviour of the capture code, unchanged by the Blender 5 port:

- A frame where detection fails contributes no sample, so captured motion has
  fewer frames than the source video and neighbouring samples end up adjacent in
  time. Whether that reads as smooth playback is untested. What is certain is
  that frame indices no longer match the video's.
- Multi-view capture combines the front and side views by list position. If
  detection fails in one view but not the other, the combined data pairs the wrong
  frames.
- The combined result takes its Z from the side view's X. This assumes both cameras
  were set up as the workflow describes and share a coordinate origin.
- `Bake Motion` with **Only Selected Bones** on and nothing selected in Pose Mode
  now cancels rather than baking every bone. Select the bones first.

### CVZone 2.x compatibility

The packaged CVZone 2.0.0 needs two corrections, applied by `nix/cvzone.patch`:
its `HandDetector` hardcodes the hand type as `Unknown` even though the Tasks API
reports handedness beside the landmarks, and it drops MediaPipe's per-landmark
depth. Without the patch both hands land in one list and hand motion is flat in Z.
Pose depth was already correct in 2.0.0.

The smoke test asserts both hands route to separate lists and that each hand's
depth equals `landmark.z * width` after normalization, for each hand separately.

---

🎓 Tutorial

A complete installation + usage tutorial is available here:

[![Watch the video](https://img.youtube.com/vi/NWfkF-sr-dY/0.jpg)](https://youtu.be/NWfkF-sr-dY)

---

🤝 Contributing

Contributions are welcome! Report issues, fix bugs, improve performance, add new
features, or contribute documentation through issues and pull requests.

---

## Credits

The following test videos included in this repository are the property of the author:

- `Front5.mp4`
- `Side5.mp4`

Other test videos were obtained from:

- [Endless Reference](https://endlessreference.com) https://youtube.com/@endlessreference

These videos are used for testing and demonstration purposes only.

---

📄 License

This project is licensed under the MIT License.
See the LICENSE file for full details.

---

💬 Support

For doubts, improvements, or help with animation/mocap:

📧 Email: larenju23@gmail.com
📂 GitHub Issues: Feel free to open one anytime.

---

🎉 Thank You for Using Open Mocap!

If this add-on helps you, consider ⭐ starring the repository!
