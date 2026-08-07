from pathlib import Path
import subprocess

repo = Path(r'C:\Users\Brito\Downloads\jarvis-fase0-nucleo\jarvis-assistant')
output = []
for cmd in [['git', '--version'], ['git', '-C', str(repo), 'status', '--short'], ['git', '-C', str(repo), 'branch', '--show-current'], ['git', '-C', str(repo), 'remote', '-v']]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output.append(f'CMD: {cmd}\nEXIT: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\n')
    except Exception as exc:
        output.append(f'CMD: {cmd}\nEXCEPTION: {exc}\n')
Path(repo / 'git_probe.txt').write_text('\n'.join(output), encoding='utf-8')
print('done')
