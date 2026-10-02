{
  lib,
  pythonPackages,
  fetchurl,
  autoPatchelfHook,
  libglvnd,
}:

pythonPackages.buildPythonPackage (finalAttrs: {
  pname = "mediapipe";
  version = "1.0.1";

  format = "wheel";

  # x86_64 is the only architecture PyPI publishes a manylinux wheel for, so the
  # aarch64 wheel under a matching filename is not available.
  src = fetchurl {
    url = "https://files.pythonhosted.org/packages/py3/m/mediapipe/mediapipe-1.0.1-py3-none-manylinux_2_28_x86_64.whl";
    hash = "sha256-EhUiJRr8PBNeS3sMNB3V4FCtHsh2MRJ0hPPDia44UEQ=";
  };

  nativeBuildInputs = [ autoPatchelfHook ];
  runtimeDependencies = [ libglvnd ];

  # matplotlib is imported at package import time by the drawing helpers, even
  # though the add-on never plots. The remaining wheel metadata (sounddevice,
  # absl-py, flatbuffers, jax) covers backends this add-on never touches.
  dependencies = with pythonPackages; [
    certifi
    matplotlib
    numpy
    opencv4
  ];

  # The wheel's own metadata lists dependencies this add-on does not import, so
  # the generic runtime-dependency check reports them as missing.
  dontCheckRuntimeDeps = "1";
  dontCheck = true;

  meta = {
    description = "Cross-platform AI framework providing the MediaPipe Tasks API";
    homepage = "https://ai.google.dev/edge/mediapipe";
    license = lib.licenses.asl20;
    platforms = lib.intersectLists lib.platforms.x86_64 lib.platforms.linux;
  };
})
