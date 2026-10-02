{
  lib,
  fetchurl,
  runCommand,
}:

# cvzone downloads these models into the working directory on first use. Fetching
# them into the store keeps tracking offline and avoids writing into Blender's
# launch directory.
let
  pose = fetchurl {
    url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task";
    hash = "sha256-WZKeHR7pUodzXd2DOxnPSsRtKbx6/du/Z1PEWWkNV0o=";
  };
  hand = fetchurl {
    url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
    hash = "sha256-+8KjAIDDxVcJO13fwzRpgTLrNBBEzO4yLM+LzzYHzeE=";
  };
in
runCommand "mediapipe-models" { } ''
  mkdir -p $out
  ln -s ${pose} $out/pose_landmarker.task
  ln -s ${hand} $out/hand_landmarker.task
''
