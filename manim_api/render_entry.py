"""Trusted runner records actual rendered geometry without modifying Qwen source."""
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import manim as m
from scene_validation import validate_code,validate_geometry


def main():
    source,quality,duration=sys.argv[1:]
    validate_code(Path(source).read_text(),manim_module=m)
    spec=importlib.util.spec_from_file_location('generated_scene',source)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observed=[]
    band_errors=[]
    original=module.GeneratedScene.update_mobjects
    last=[-.5]
    def monitored(scene,dt):
        original(scene,dt)
        if scene.time-last[0]<.45:
            return
        last[0]=scene.time
        boxes=[]
        arrows=[]
        reference_lines=[]
        labels=[]
        fills=[]
        seen=set()
        for obj in scene.mobjects:
            points=obj.get_all_points()
            if len(points)==0 or not np.isfinite(points).all():
                continue
            low,high=points.min(axis=0),points.max(axis=0)
            boxes.append({'type':type(obj).__name__,'min':low[:2].tolist(),'max':high[:2].tolist()})
            for member in obj.get_family():
                if id(member) in seen:
                    continue
                seen.add(id(member))
                if isinstance(member,m.Text) and not getattr(member,'_lesson_reserved',None):
                    if member.get_fill_opacity()>=.8:
                        # Text's container can report black while its SVG glyphs
                        # carry the displayed color. Inspect actual filled glyphs.
                        inks={glyph.get_fill_color().to_hex() for glyph in member.get_family()
                              if isinstance(glyph,m.VMobject) and len(glyph.points)>0 and glyph.get_fill_opacity()>=.8}
                        labels.append({'text':member.original_text,'min':member.get_corner(m.DL)[:2].tolist(),
                                       'max':member.get_corner(m.UR)[:2].tolist(),
                                       'color':next(iter(inks)) if len(inks)==1 else None})
                    if member.get_top()[1]>2.9 or member.get_bottom()[1]<-2.9:
                        band_errors.append({'time':float(scene.time),'text':member.original_text,
                                            'top':float(member.get_top()[1]),'bottom':float(member.get_bottom()[1])})
                if isinstance(member,m.Rectangle) and member.get_fill_opacity()>=.8:
                    fills.append({'min':member.get_corner(m.DL)[:2].tolist(),
                                  'max':member.get_corner(m.UR)[:2].tolist(),
                                  'color':member.get_fill_color().to_hex()})
                if isinstance(member,m.Arrow):
                    arrows.append({'start':member.get_start().tolist(),'end':member.get_end().tolist(),
                                   'length':float(np.linalg.norm(member.get_end()-member.get_start())),
                                   'color':member.get_color().to_hex()})
                elif isinstance(member,m.Line) and member.get_color().to_hex().lower()=='#edf3ff':
                    reference_lines.append({'start':member.get_start().tolist(),'end':member.get_end().tolist()})
        observed.append({'time':float(scene.time),'boxes':boxes,'arrows':arrows,'text_labels':labels,
                         'reference_lines':reference_lines,'filled_rectangles':fills})
    module.GeneratedScene.update_mobjects=monitored
    height,width,fps=(480,854,15) if quality=='preview' else (1080,1920,30)
    with m.tempconfig({'pixel_height':height,'pixel_width':width,'frame_rate':fps,
                       'media_dir':'media','output_file':'clip','preview':False,
                       'disable_caching':True,'verbosity':'WARNING'}):
        scene=module.GeneratedScene()
        scene.render()
        elapsed=float(scene.time)
        output=str(scene.renderer.file_writer.movie_file_path)
    overflow=[]
    for sample in observed:
        for box in sample['boxes']:
            if box['min'][0]<-7.25 or box['max'][0]>7.25 or box['min'][1]<-4.15 or box['max'][1]>4.15:
                overflow.append({'time':sample['time'],**box})
    data={'duration':elapsed,'requested_duration':float(duration),'output':output,
          'frame_size':[width,height],'fps':fps,'out_of_frame':overflow,'reserved_band_text':band_errors,'samples':observed}
    Path('geometry.json').write_text(json.dumps(data,indent=2)+'\n')
    validate_geometry(data)
    if overflow:
        raise ValueError('Rendered objects leave the video frame: '+json.dumps(overflow[:3]))
    if band_errors:
        raise ValueError('Extra body text invades the reserved title/caption bands; keep its complete bounding box between y=-2.9 and y=2.9: '+json.dumps(band_errors[:3]))
    if elapsed>float(duration)+max(2,float(duration)*.2):
        raise ValueError(f'Scene ran for {elapsed:.1f}s instead of approximately {duration}s')


if __name__=='__main__':main()
