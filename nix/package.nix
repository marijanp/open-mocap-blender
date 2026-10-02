{
  lib,
  stdenvNoCC,
}:

stdenvNoCC.mkDerivation {
  pname = "open-mocap-blender";
  version = "1.1.0";

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../__init__.py
      ../blender_manifest.toml
      ../dependencies.py
      ../globalVariables.py
      ../operators.py
      ../panels.py
      ../utils.py
      # The manifest declares an MIT license, so the license text ships with the
      # add-on as Blender requires.
      ../LICENSE.txt
    ];
  };

  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/blender/extensions/open_mocap
    cp -r . $out/share/blender/extensions/open_mocap
    runHook postInstall
  '';

  meta = {
    description = "Blender add-on for AI-powered motion capture";
    homepage = "https://github.com/Larenju-Rai/open-mocap-blender";
    license = lib.licenses.mit;
    platforms = lib.platforms.all;
  };
}
