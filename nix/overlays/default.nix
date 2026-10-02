/*
  The add-on runs inside Blender, so its Python dependencies are built for the
  interpreter Blender embeds rather than the default one. Deriving from
  blender.python keeps the two in step.

  These attributes are this fork's own packaging, not a library interface: the
  dev shell is the reason they exist. Treat them as private.
*/
final: _prev:

let
  inherit (final) lib blender;

  # The add-on and its dependency set were verified against Blender's Python
  # 3.13. A different minor version needs those versions re-verified before use,
  # so refuse rather than produce an environment that cannot import them.
  #
  # Kept lazy (applied where the interpreter is consumed) because forcing it
  # while the overlay result is being assembled recurses through `final`.
  requireSupportedPython =
    interpreter:
    if lib.hasPrefix "3.13." interpreter.version then
      interpreter
    else
      throw ''
        open-mocap-blender targets Blender's embedded Python 3.13.x,
        but this Blender embeds ${interpreter.version}.
        Re-verify the pinned mediapipe/cvzone/numpy/OpenCV versions against that
        interpreter before using this overlay.
      '';

  # Named blenderPython rather than python: nixpkgs reserves `python` for Python 2.
  blenderPython = requireSupportedPython blender.python;
  pythonPackages = blender.pythonPackages;

  mediapipe = final.callPackage ../mediapipe.nix { inherit pythonPackages; };
  cvzone = final.callPackage ../cvzone.nix { inherit mediapipe pythonPackages; };
in
{
  # The add-on, as a Blender extension. Platform-independent; it is plain Python
  # that only needs its dependencies importable.
  open-mocap-blender = final.callPackage ../package.nix { };

  # The dependency environment and the MediaPipe models, exported by the dev
  # shell below. CVZone downloads models into the working directory on first use,
  # which is neither offline nor writable under the Nix store.
  open-mocap-python-env = blenderPython.withPackages (ps: [
    cvzone
    mediapipe
    ps.numpy
    ps.opencv4
  ]);
  mediapipe-models = final.callPackage ../models.nix { };

  devShell = final.mkShell {
    packages = [
      blender
      final.open-mocap-blender
    ];

    shellHook = ''
      export CVZONE_MODEL_DIR="${final.mediapipe-models}"
      export PYTHONPATH="${final.open-mocap-python-env}/${blenderPython.sitePackages}''${PYTHONPATH:+:$PYTHONPATH}"

      # Extensions are only discovered under a repository name, and Blender writes
      # a cache beside them, so the built add-on is symlinked into the user's
      # extensions directory instead of being served from the read-only store.
      # Plain `blender` then finds it; enable it once in Preferences ▸ Add-ons.
      export BLENDER_USER_EXTENSIONS="''${BLENDER_USER_EXTENSIONS:-''${XDG_DATA_HOME:-$HOME/.local/share}/blender/extensions}"
      mkdir -p "$BLENDER_USER_EXTENSIONS/user_default"
      ln -sfn ${final.open-mocap-blender}/share/blender/extensions/open_mocap \
        "$BLENDER_USER_EXTENSIONS/user_default/open_mocap"
    '';
  };
}
