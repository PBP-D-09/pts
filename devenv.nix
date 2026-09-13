{
  pkgs,
  ...
}:
{
  packages = with pkgs; [
    # Package management
    python3Packages.pip

    # System libraries required for common Django dependencies
    zlib
    libjpeg
    libpng
    gettext # Required for Django internationalization (makemessages)
  ];

  languages = {
    python = {
      enable = true;
      version = "3.14";

      venv = {
        enable = true;
        quiet = true;
      };

      uv = {
        enable = true;
        sync.enable = true;
      };
    };

    javascript = {
      enable = true;
      package = pkgs.nodejs_22;

      npm = {
        enable = true;
      };
    };
  };

  # services = {
  #   postgres = {
  #     enable = true;
  #     package = pkgs.postgresql_18;
  #     initialDatabases = [ { name = "django_dev"; } ];
  #     listen_addresses = "127.0.0.1";
  #     port = 55432;
  #   };
  #
  #   redis = {
  #     enable = true;
  #     port = 63799;
  #   };
  # };

  enterShell = ''
    echo "🐍 Fullstack Django Environment Ready"
    echo "   - Python: $(python --version)"
    # echo "   - uv:     $(uv --version)"
    echo "   - pip:    $(pip --version)"
    echo ""
  '';

  scripts = {
    dev.exec = "devenv up";
  };

  git-hooks.hooks = {
    ruff.enable = true;
    ruff-format.enable = true;
    djlint = {
      enable = true;
      name = "djlint format";
      entry = "uv run djlint --reformat";
      types = [ "html" ];
    };
  };
}
