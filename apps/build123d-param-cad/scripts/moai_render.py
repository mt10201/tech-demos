import os
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
import numpy as np, trimesh, pyrender
from PIL import Image, ImageDraw

def look_at(eye, target, up=(0,0,1)):
    eye=np.asarray(eye,float); target=np.asarray(target,float); up=np.asarray(up,float)
    f = target-eye; f/=np.linalg.norm(f)
    if abs(f@up)>0.99: up=np.array([0,1.0,0])
    s=np.cross(f,up); s/=np.linalg.norm(s); u=np.cross(s,f)
    P=np.eye(4); P[:3,0]=s; P[:3,1]=u; P[:3,2]=-f; P[:3,3]=eye
    return P

_r = None
def render(m, path, direction, target=None, mag=None, size=(800,900), title="", color=(0.62,0.56,0.50), smooth=False):
    global _r
    if _r is None or (_r.viewport_width, _r.viewport_height) != tuple(size):
        if _r is not None:
            _r.delete()
        _r = pyrender.OffscreenRenderer(*size)
    if target is None: target = m.bounds.mean(0)
    if mag is None: mag = 0.62*np.ptp(m.bounds,0).max()
    d = np.asarray(direction,float); d/=np.linalg.norm(d)
    sc = pyrender.Scene(bg_color=[0.84,0.9,0.94,1], ambient_light=[0.18,0.18,0.18])
    mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=[*color,1], metallicFactor=0.0, roughnessFactor=0.85)
    sc.add(pyrender.Mesh.from_trimesh(m, material=mat, smooth=smooth))
    eye = np.asarray(target)+d*600
    pose = look_at(eye, target)
    sc.add(pyrender.OrthographicCamera(xmag=mag*size[0]/size[1], ymag=mag, znear=1, zfar=2000), pose=pose)
    # key light from camera-upper-left, fill from other side
    sc.add(pyrender.DirectionalLight(intensity=3.2), pose=look_at(np.asarray(target)+600*(d+np.array([0.4,0,0.7])), target))
    sc.add(pyrender.DirectionalLight(intensity=1.2), pose=look_at(np.asarray(target)+600*(d+np.array([-0.6,0,-0.2])), target))
    c,_ = _r.render(sc)
    im = Image.fromarray(c)
    if title:
        ImageDraw.Draw(im).text((10,10), title, fill=(0,0,0))
    im.save(path); return path

def board(paths, out, title, cols=None):
    imgs=[Image.open(p).convert("RGB") for p in paths]
    cols = cols or len(imgs); rows=(len(imgs)+cols-1)//cols
    w=max(i.width for i in imgs); h=max(i.height for i in imgs)
    B=Image.new("RGB",(cols*w+(cols+1)*8, rows*h+(rows+1)*8+30),(255,255,255))
    ImageDraw.Draw(B).text((10,8),title,fill=(0,0,0))
    for k,i in enumerate(imgs):
        B.paste(i,(8+(k%cols)*(w+8), 38+(k//cols)*(h+8)))
    B.save(out); return out
