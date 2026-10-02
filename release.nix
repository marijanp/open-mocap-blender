let
  sources = import ./npins;
  pkgs = import sources.nixpkgs {
    overlays = [
      (import ./nix/overlays/default.nix)
    ];
  };
in
{
  inherit (pkgs)
    devShell
    open-mocap-blender
    ;
}
