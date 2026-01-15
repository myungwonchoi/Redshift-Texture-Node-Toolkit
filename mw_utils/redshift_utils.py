import c4d # 모듈이여도 c4d는 항상 필요
import maxon
import os
import re

# --- Constants & Node IDs ---
ID_RS_NODESPACE = maxon.Id("com.redshift3d.redshift4c4d.class.nodespace")
ID_RS_STANDARD_MATERIAL = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.standardmaterial")
ID_RS_OUTPUT = maxon.Id("com.redshift3d.redshift4c4d.node.output")
ID_RS_TEXTURESAMPLER = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.texturesampler")
ID_RS_BUMPMAP = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.bumpmap")
ID_RS_DISPLACEMENT = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.displacement")
ID_RS_UV_CONTEXT_PROJECTION = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.uvcontextprojection")
ID_RS_MATH_VECTOR_MULTIPLY = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.rsmathmulvector")

ID_RS_MATH_ABS = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.rsmathabs")
ID_RS_MATH_ABS_VECTOR = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.rsmathabsvector")
ID_RS_TRIPLANAR = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.triplanar")
ID_RS_MATH_INVERT = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.rsmathinv")

# Port IDs
PORT_RS_STD_BASE_COLOR = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.base_color"
PORT_RS_STD_METALNESS = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.metalness"
PORT_RS_STD_ROUGHNESS = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.refl_roughness"
PORT_RS_STD_SPECULAR = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.refl_weight"
PORT_RS_STD_OPACITY = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.opacity_color"
PORT_RS_STD_EMISSION = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.emission_color"
PORT_RS_STD_BUMP_INPUT = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.bump_input"

PORT_RS_TEX_PATH = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.tex0" # This is the group, path is child
PORT_RS_TEX_SCALE = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.scale"
PORT_RS_TEX_OFFSET = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.offset"
PORT_RS_TEX_ROTATE = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.rotate"
PORT_RS_TEX_OUTCOLOR = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.outcolor"
PORT_RS_TEX_UV_CONTEXT = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.uv_context"

PORT_RS_TRI_IMAGE_X = "com.redshift3d.redshift4c4d.nodes.core.triplanar.imagex"
PORT_RS_TRI_SCALE = "com.redshift3d.redshift4c4d.nodes.core.triplanar.scale"
PORT_RS_TRI_OFFSET = "com.redshift3d.redshift4c4d.nodes.core.triplanar.offset"
PORT_RS_TRI_ROTATE = "com.redshift3d.redshift4c4d.nodes.core.triplanar.rotation"
PORT_RS_TRI_OUTCOLOR = "com.redshift3d.redshift4c4d.nodes.core.triplanar.outcolor"

PORT_RS_BUMP_INPUT = "com.redshift3d.redshift4c4d.nodes.core.bumpmap.input"
PORT_RS_BUMP_OUT = "com.redshift3d.redshift4c4d.nodes.core.bumpmap.out"
PORT_RS_BUMP_TYPE = "com.redshift3d.redshift4c4d.nodes.core.bumpmap.inputtype"
PORT_RS_MATH_VECTOR_MULTIPLY_INPUT2 = "com.redshift3d.redshift4c4d.nodes.core.rsmathmulvector.input2"

PORT_RS_MATH_INVERT_INPUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathinv.input"

PORT_RS_UV_CONTEXT_PROJECTION_OUTCONTEXT = "com.redshift3d.redshift4c4d.nodes.core.uvcontextprojection.outcontext"
PORT_RS_UV_CONTEXT_PROJECTION_PROJECTION = "com.redshift3d.redshift4c4d.nodes.core.uvcontextprojection.proj_type"
# 000 Passthrough, # 001 UV Channel, # 002 Triplanar

PORT_RS_MATH_ABS_INPUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathabs.input"
PORT_RS_MATH_ABS_OUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathabs.out"

PORT_RS_MATH_ABS_VECTOR_INPUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathabsvector.input"
PORT_RS_MATH_ABS_VECTOR_OUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathabsvector.out"

PORT_RS_DISP_TEXMAP = "com.redshift3d.redshift4c4d.nodes.core.displacement.texmap"
PORT_RS_DISP_OUT = "com.redshift3d.redshift4c4d.nodes.core.displacement.out"
PORT_RS_OUTPUT_DISPLACEMENT = "com.redshift3d.redshift4c4d.node.output.displacement"

# Colorspace
RS_INPUT_COLORSPACE_RAW = "RS_INPUT_COLORSPACE_RAW"

def create_texture_node(graph, texture_path):
    """Creates a Texture Sampler node and sets the path."""
    tex_node = graph.AddChild(maxon.Id(), ID_RS_TEXTURESAMPLER)
    
    # Set Texture Path
    path_port = tex_node.GetInputs().FindChild(PORT_RS_TEX_PATH).FindChild("path")
    if path_port.IsValid():
        path_port.SetPortValue(texture_path)
    
    return tex_node

def find_standard_material_and_output(graph):
    """Finds the Standard Material and Output node in the graph."""
    standard_mat = None
    output_node = None
    
    root = graph.GetRoot()
    for node in root.GetInnerNodes(mask=maxon.NODE_KIND.NODE, includeThis=False):
        asset_id = node.GetValue("net.maxon.node.attribute.assetid")[0]
        if asset_id == ID_RS_STANDARD_MATERIAL:
            standard_mat = node
        elif asset_id == ID_RS_OUTPUT:
            output_node = node
            
    return standard_mat, output_node

def remove_connections(node, port_id):
    """
    특정 노드의 특정 포트에 연결된 모든 연결을 제거합니다.
    """
    if not node or not node.IsValid():
        return

    input_ports = node.GetInputs().GetChildren() # 입력 포트 리스트
    for input_port in input_ports:
        port_name = input_port.GetId().ToString()
        if port_name == port_id:
            # 각 포트에 연결된 선(Connection) 가져오기
            connections = []
            input_port.GetConnections(maxon.PORT_DIR.INPUT, connections)
            for connection in connections:
                source_port = connection[0] # 연결된 소스 포트 (출력 포트)
                # RemoveConnection(source, destination)
                maxon.GraphModelHelper.RemoveConnection(source_port, input_port)
            break # 포트를 찾았으므로 루프 종료


TEXTURE_CHANNELS = {
    "base_color":        [
        "basecolor", "base", "color", "albedo", "diffuse", "diff", 
        "col", "bc", "alb", "rgb" , "d"
    ],
    "normal":       [
        "normal", "norm", "nrm", "nml", "nrml", "n" 
    ],
    "bump":         [
        "bump", "b"
    ],
    "ao":           [
        "ao", "ambient", "occlusion", "occ", "amb"
    ],
    "metalness":    [
        "metallic", "metalness", "metal", "mtl", "met", "m"
    ],
    "refl_roughness":    [
        "roughness", "rough", "rgh", "r"
    ],
    "refl_weight":     [
        "specular", "spec", "s", "refl", "reflection"
    ],
    "glossiness":   [
        "glossiness", "gloss", "g"
    ],
    "opacity_color":      [
        "opacity", "opac", "alpha", "transparency", "transparent", 
        "o", "a", "mask", "cutout" # 알파 마스크용 용어 추가
    ],
    "translucency": [
        "translucency", "transmission", "trans", 
        "sss", "subsurface", "scatter", "scattering" # SSS 관련 용어 보강
    ],
    "displacement": [
        "displacement", "disp", "dsp", 
        "height", "h"
    ],
    "emission_color":     [
        "emissive", "emission", "emit", "illu", "illumination", "selfillum"
    ]
}

def _split_into_components(fname):
    """
    Split filename into components with prefix filtering
    'D_Wood_Maple_01_ROUGH_1.jpg' -> ['wood', 'maple', 'rough']
    """
    # Remove extension
    fname = os.path.splitext(fname)[0]

    # [NEW] Discard prefix: Keep string only after the LAST underscore
    if "_" in fname:
        # 마지막 _ 뒤의 부분만 가져옴
        fname = fname.rsplit("_", 1)[-1]
    else:
        # 언더바가 없으면 조건에 맞지 않으므로 빈 리스트 반환
        return []

    # Remove digits
    fname = "".join(i for i in fname if not i.isdigit())

    # Separate CamelCase by space
    fname = re.sub(r"([a-z])([A-Z])", r"\g<1> \g<2>", fname)

    # Replace common separators with SPACE
    separators = ["_", ".", "-", "__", "--", "#"]
    for sep in separators:
        fname = fname.replace(sep, " ")

    components = fname.split(" ")
    components = [c.lower() for c in components if c.strip()]
    return components

def GetTextureChannel(fname):
    """
    파일명의 마지막 '_' 뒤의 단어를 추출하여 채널을 판별합니다.
    점수 계산 없이 정확히 일치하는 키워드가 있으면 해당 채널을 반환합니다.
    """
    # 1. 확장자 제거
    base_name = os.path.splitext(fname)[0]
    
    # 2. '_'가 없으면 판별 불가
    if "_" not in base_name:
        return None
        
    # 3. 마지막 '_' 뒤의 단어 추출 및 소문자 변환
    suffix = base_name.rsplit("_", 1)[-1].lower()
    
    # 4. 채널 매칭 확인
    for channel, keywords in TEXTURE_CHANNELS.items():
        if suffix in keywords:
            return channel
            
    return None

def set_colorspace_raw(node):
    """
    Sets the colorspace of a texture node to RAW.
    """
    tex0_port = node.GetInputs().FindChild(PORT_RS_TEX_PATH)
    if tex0_port.IsValid():
        colorspace_port = tex0_port.FindChild("colorspace")
        if colorspace_port.IsValid():
            colorspace_port.SetPortValue(RS_INPUT_COLORSPACE_RAW)
