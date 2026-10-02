{
  lib,
  pythonPackages,
  fetchurl,
  mediapipe,
}:

pythonPackages.buildPythonPackage (finalAttrs: {
  pname = "cvzone";
  version = "2.0.0";

  pyproject = true;

  src = fetchurl {
    url = "https://files.pythonhosted.org/packages/source/c/cvzone/cvzone-2.0.0.tar.gz";
    hash = "sha256-JMJ+bUHtqHZfb3jEwvJlQXiJdOpzXQe7bruPyIFsCac=";
  };

  build-system = [ pythonPackages.setuptools ];

  dependencies = [
    mediapipe
    pythonPackages.numpy
    pythonPackages.opencv4
  ];

  patches = [ ./cvzone.patch ];

  # Upstream declares `opencv-python`, which this package supplies as nixpkgs'
  # OpenCV instead; the runtime-dependency check only knows the upstream name.
  dontCheckRuntimeDeps = "1";

  # The bundled demo modules download models and open camera windows, so there
  # is nothing worth importing here; tests/smoke.py covers the real entry points.
  dontCheck = true;

  meta = {
    description = "Computer vision wrappers around the MediaPipe Tasks API";
    homepage = "https://www.computervision.zone";
    license = lib.licenses.mit;
    # Pure Python, but it imports mediapipe, which is x86_64 Linux only.
    platforms = lib.intersectLists lib.platforms.x86_64 lib.platforms.linux;
  };
})
