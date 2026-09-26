"""Build a native Finder launcher for this checkout and its existing .venv."""
import argparse
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile


def build_app(destination: Path, root: Path):
    destination = destination.resolve()
    contents = destination / 'Contents'
    executable = contents / 'MacOS' / 'Noah'
    executable.parent.mkdir(parents=True, exist_ok=True)
    launcher = root.resolve() / 'scripts' / 'launch-macos.sh'
    source = '#include <unistd.h>\nint main(void) {\n'
    source += 'execl("/bin/zsh", "zsh", ' + json.dumps(str(launcher), ensure_ascii=False) + ', (char *)0);\nreturn 1;\n}\n'
    with tempfile.TemporaryDirectory(prefix='noah-build-') as temporary:
        cfile = Path(temporary) / 'launcher.c'
        cfile.write_text(source)
        subprocess.run(['clang', str(cfile), '-o', str(executable)], check=True)
    with (contents / 'Info.plist').open('wb') as stream:
        plistlib.dump({
            'CFBundleName': 'Noah',
            'CFBundleDisplayName': 'Noah',
            'CFBundleIdentifier': 'local.projectnoah.launcher',
            'CFBundleExecutable': 'Noah',
            'CFBundlePackageType': 'APPL',
            'CFBundleVersion': '1',
            'CFBundleShortVersionString': '0.1',
            'LSUIElement': True,
            'NSHighResolutionCapable': True,
        }, stream)
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(build_app(args.destination, Path(__file__).resolve().parents[1]))


if __name__ == '__main__':
    main()
