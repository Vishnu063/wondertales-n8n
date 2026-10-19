"""Hypit is the actual compositor. FFmpeg only validates and burns supplied captions."""
import json
from pathlib import Path
import shutil
import subprocess
import textwrap


def command(args, *, cwd=None, timeout=120):
    result = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Never include provider output: it can contain session URLs or auth material.
        raise RuntimeError(f"{Path(str(args[0])).name} failed. Check local tool setup and compatibility.")
    return result.stdout


def probe(path, duration=None, aspect=None, min_size=1):
    data = json.loads(command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if not video or not audio or min(video["width"], video["height"]) < min_size:
        raise ValueError("Video needs a picture, an audio stream and the expected resolution")
    actual = float(data["format"]["duration"])
    if duration is not None and abs(actual - duration) > 0.65:
        raise ValueError("Video duration differs from the requested scene length")
    if aspect is not None:
        w, h = map(int, aspect.split(":"))
        if abs(video["width"]/video["height"] - w/h) > .025:
            raise ValueError("Video aspect ratio does not match the plan")
    command(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"], timeout=600)
    return {"duration": actual, "width": video["width"], "height": video["height"], "has_audio": True,
            "checks": "Decoded successfully. Speech accuracy and visual continuity still need human review."}


def author_project(work, job, chrome=""):
    work = Path(work)
    (work / "package.json").write_text('{"private":true,"hypit":{"project":true}}')
    w, h = (720, 1280) if job["aspect"] == "9:16" else (1280, 720)
    imports = {"time": "timeline-author", "space": "spatial", "asset": "media", "op": "media-operations",
               "visual": "visual-track", "audio": "audio-track", "film": "film", "html": "html-video"}
    lines = ['<?svml using="@hypit/markup@1"?>', '<svml>']
    lines += [f'<import as="{a}" from="@hypit/{p}@1"/>' for a, p in imports.items()]
    lines += ['<import as="look" source="./film.svs"/>']
    lines += ['<time:Clock id="clock" frame-rate="30"/>',
              f'<time:Timeline id="program" clock={{clock}} end="{job["duration"]}s">']
    for i, _ in enumerate(job["scenes"]):
        lines.append(f'<time:Window id="s{i}" from="{i*8}s" for="8s"/>')
    lines += ['</time:Timeline>', f'<space:Canvas id="canvas" width="{w}" height="{h}"/>']
    for i, _ in enumerate(job["scenes"]):
        lines += [f'<asset:Video id="file{i}" src="./assets/scene-{i}.mp4"/>',
                  f'<op:Normalize id="clip{i}" source={{file{i}}} clock={{clock}} video="primary-moving" audio="default" span-authority="video"/>']
    lines += ['<visual:Track id="picture" timeline={program.timeline}>']
    for i, _ in enumerate(job["scenes"]):
        lines.append(f'<visual:Clip media={{clip{i}.media}} during={{program.s{i}}} frame={{canvas.bounds}} z="10" fit="contain"/>')
    lines += ['</visual:Track>', '<audio:Track id="sound" timeline={program.timeline}>']
    for i, _ in enumerate(job["scenes"]):
        lines.append(f'<audio:Clip source={{clip{i}.media}} during={{program.s{i}}}/>')
    lines += ['</audio:Track>', '<film:Film id="main" canvas={canvas.canvas} timeline={program.timeline} appearance={look.film.main}>',
              '<film:Track source={picture.visual}/>', '<film:Track source={sound.audio}/>', '</film:Film>',
              '<html:Video id="final" composition={main.composition} timeline={program.timeline}/>', '</svml>']
    (work / "film.svml").write_text('\n'.join(lines))
    (work / "film.svs").write_text('<?svml using="@hypit/recipe@1"?>\n<sheet version="1">film.main { background: #18212A; }</sheet>\n')
    (work / "film.svrun").write_text('<?svml using="@hypit/markup/run@1"?>\n<svrun version="1"><author source="./film.svml"/><target output="final.video"/></svrun>')
    html_config = {"workers": 1, "maxWorkers": 1, "browserCapacity": 1}
    if chrome:
        html_config["chromePath"] = chrome
    profile = {"format": "hypit.runtime-local@1", "dataRoot": ".hypit/execution", "credentials": {},
               "endpoints": {"media.local": {"use": "@hypit/media-local"},
                             "html.local": {"use": "@hypit/provider-html-local", "config": html_config}}, "bindings": {}}
    (work / "hypit.runtime.json").write_text(json.dumps(profile, indent=2))
    (work / ".hypit").mkdir(exist_ok=True)
    (work / ".hypit/runtime").write_text("hypit.runtime.json\n")
    (work / "BRIEF.md").write_text(f"# {job['title']}\n\n{job['story']}\n\nLanguage: {job['language']}; style: {job['style']}\n")
    (work / "plan.json").write_text(json.dumps(job, ensure_ascii=False, indent=2))
    return work


def timestamp(seconds):
    return f"{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02},000"


def render(work, job, hypit, save_build, build_id=None):
    work = Path(work)
    def run(*args, timeout=120):
        scope = ["--project", work]
        if args[0] in ("plan", "build", "status"):
            scope += ["--runtime", work / "hypit.runtime.json"]
        return command([hypit, *args, *scope], cwd=work, timeout=timeout)
    run("check", "film.svrun")
    # Only local media and HTML endpoints exist: there is no generation billing account.
    run("plan", "film.svrun")
    if build_id is None:
        result = json.loads(run("build", "film.svrun", "--json"))
        build_id = result["build"]["id"]
        save_build(build_id)
    # Reattach an existing build after interruption; never silently create another.
    run("status", build_id, "--watch", "--max-wait-ms", "3600000", "--json", timeout=3700)
    run("get", build_id, "--output", "final.video", "--to", work / "hypit.mp4")
    subtitles = []
    for i, s in enumerate(job["scenes"]):
        subtitles.append(f"{i+1}\n{timestamp(i*8)} --> {timestamp((i+1)*8)}\n" + '\n'.join(textwrap.wrap(s["narration"], 36)) + '\n')
    (work / "captions.srt").write_text('\n'.join(subtitles), encoding="utf-8")
    command(["ffmpeg", "-v", "error", "-y", "-i", "hypit.mp4", "-vf",
             "subtitles=captions.srt:force_style='FontName=Noto Sans,FontSize=18,Outline=2,MarginV=36'",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", "final.mp4"], cwd=work, timeout=1200)
    return probe(work / "final.mp4", job["duration"], job["aspect"], min_size=720)


def local_hypit():
    path = Path(__file__).resolve().parent.parent / "node_modules/.bin/hypit"
    return str(path) if path.exists() else shutil.which("hypit")
