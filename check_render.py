"""Extract multiple checkpoints per scene and verify the MP4 stream."""
import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--name", default="preview")
    parser.add_argument("--timings",type=Path,default=ROOT/"artifacts/scene-timings.json")
    args = parser.parse_args()
    probe = subprocess.run(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(args.video)],
                           capture_output=True,text=True,check=True)
    metadata = json.loads(probe.stdout)
    timeline = json.loads(args.timings.read_text())
    stream = next(s for s in metadata["streams"] if s["codec_type"]=="video")
    assert stream["codec_name"]=="h264"
    assert abs(float(metadata["format"]["duration"])-timeline[-1]["end"]) < 0.2
    folder = ROOT/"artifacts"/args.name
    folder.mkdir(parents=True,exist_ok=True)
    sheet = Image.new("RGB",(4*480,7*300),"#0b1220")
    draw = ImageDraw.Draw(sheet)
    for row, scene in enumerate(timeline):
        for col,fraction in enumerate((0.22,0.44,0.66,0.82)):
            t = scene["start"]+(scene["end"]-scene["start"])*fraction
            path = folder/f'{scene["id"]}-{col+1}.png'
            subprocess.run(["ffmpeg","-v","error","-y","-ss",str(t),"-i",str(args.video),
                            "-frames:v","1","-vf","scale=1280:-1",str(path)],check=True)
            im = Image.open(path).convert("RGB")
            im.thumbnail((480,270))
            sheet.paste(im,(col*480,row*300+25))
            draw.text((col*480+6,row*300+5),f'{scene["id"]} · {t:.1f}s',fill="white")
    sheet.save(folder/"contact-sheet.jpg")
    (folder/"metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    print(json.dumps({"video":str(args.video.resolve()),"duration":metadata["format"]["duration"],
                      "width":stream["width"],"height":stream["height"],"fps":stream["avg_frame_rate"],
                      "contact_sheet":str(folder/"contact-sheet.jpg")},indent=2))


if __name__=="__main__": main()
