import c4d
import maxon
import os
import sys
import ctypes
from ctypes import wintypes

# redshift_utils 경로 추가
current_dir = os.path.dirname(__file__)
sub_dir = os.path.join(current_dir, "mw_utils")
if sub_dir not in sys.path:
    sys.path.append(sub_dir)

import redshift_utils

# --- Plugin ID ---
PLUGIN_ID = 1067297

# --- Channel Suffixes ---
# CHANNEL_SUFFIXES = {
#     "diffuse_color": "BaseColor", # RS Material
#     "base_color": "BaseColor", # Standard Material
#     "normal": "Normal",
#     "ao": "AO",
#     "refl_metalness": "Metalic", # RS Material    
#     "metalness": "Metalic", # Standard Material
#     "refl_roughness": "Roughness",
#     "refl_weight": "Specular",
#     "glossiness": "Glossiness",
#     "opacity_color": "Opacity",
#     "translucency": "Translucency",
#     "bump" : "Bump",
#     "displacement" : "Displacement",
#     "emission_color" : "Emissive"
# }

def ask_open_filenames(title="Select Files"):
    """
    Opens a native Windows file dialog for multi-file selection using ctypes.
    Returns a list of selected file paths.
    """
    # Constants
    OFN_ALLOWMULTISELECT = 0x00000200
    OFN_EXPLORER = 0x00080000
    OFN_FILEMUSTEXIST = 0x00001000
    
    # Structure definition
    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", wintypes.LPVOID),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", wintypes.LPVOID),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    # Buffer for file names (64KB should be enough for many files)
    max_file_buffer = 65536 
    file_buffer = ctypes.create_unicode_buffer(max_file_buffer)
    
    # Filter: Display Name\0Pattern\0...
    filter_str = "Image Files\0*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr;*.hdr;*.psd;*.tga\0All Files\0*.*\0\0"
    
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = 0 
    ofn.lpstrFilter = filter_str
    ofn.lpstrFile = ctypes.cast(file_buffer, wintypes.LPWSTR)
    ofn.nMaxFile = max_file_buffer
    ofn.lpstrTitle = title
    ofn.Flags = OFN_ALLOWMULTISELECT | OFN_EXPLORER | OFN_FILEMUSTEXIST
    
    if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
        # Parse the result buffer
        files = []
        current_str = ""
        i = 0
        while i < max_file_buffer:
            char = file_buffer[i]
            if char == '\0':
                if not current_str:
                    # Double null hit (empty string after a null) -> End of list
                    break
                files.append(current_str)
                current_str = ""
            else:
                current_str += char
            i += 1
            
        if not files:
            return []
            
        if len(files) == 1:
            return files # Single file full path
        else:
            # Multi-select: First element is directory, rest are filenames
            directory = files[0]
            return [os.path.join(directory, f) for f in files[1:]]
            
    return []

class CreatePBRMaterialCommand(c4d.plugins.CommandData):
    def Execute(self, doc):
        # 0. Load Textures (Windows API Multi-Select)
        texture_files = ask_open_filenames(title="Load Texture Files...")

        if not texture_files:
            return True

        # 1. Always Create New Redshift Material
        c4d.CallCommand(300001026) # Deselect All Materials
        c4d.CallCommand(1040264, 1012) # Materials > Redshift > Standard Material
        
        doc = c4d.documents.GetActiveDocument()
        mat = doc.GetActiveMaterial()
        if not mat:
            return True

        nodeMaterial = mat.GetNodeMaterialReference()
        # if not nodeMaterial.HasSpace(redshift_utils.ID_RS_NODESPACE):
        #     c4d.gui.MessageDialog("선택한 머티리얼이 레드쉬프트 노드 머티리얼이 아닙니다.")
        #     return True

        graph = nodeMaterial.GetGraph(redshift_utils.ID_RS_NODESPACE)
        if graph.IsNullValue():
            return True

        # 2. Find Standard Material
        standard_mat, output_node = redshift_utils.find_standard_material_and_output(graph)
        
        # if not standard_mat:
        #     c4d.gui.MessageDialog("Standard Material 노드를 찾을 수 없습니다.")
        #     return True

        # Logic: If 1 file selected, find others with same prefix
        if len(texture_files) == 1:
            sel_path = texture_files[0]
            dirname = os.path.dirname(sel_path)
            basename = os.path.basename(sel_path)

            if "_" in basename:
                prefix = basename.split("_")[0]
                # Extensions from filter_str
                valid_exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".hdr", ".psd", ".tga"}
                
                found_files = []
                try:
                    for f in os.listdir(dirname):
                        if f.startswith(prefix):
                            ext = os.path.splitext(f)[1].lower()
                            if ext in valid_exts:
                                found_files.append(os.path.join(dirname, f))
                    
                    if found_files:
                        texture_files = found_files
                except Exception as e:
                    print(f"Directory scan error: {e}")

        # 5. Process Textures
        created_nodes = []
        
        # 같은 채널에 여러 번 연결하지 않기 위한 플래그
        connected_flags = {
            "base_color": False,
            "metalness": False,
            "refl_roughness": False,
            "refl_weight": False,
            "opacity_color": False,
            "emission_color": False,
            "bump_input": "", # For both bump and normal
            "displacement": False
        }

        with graph.BeginTransaction() as transaction:
            for tex_path in texture_files:
                # Create Texture Node
                tex_node = redshift_utils.create_texture_node(graph, tex_path)
                created_nodes.append(tex_node)
                
                # 파일 이름 추출
                fname = os.path.basename(tex_path)

                # 채널 감지
                channel = redshift_utils.GetTextureChannel(fname)
                
                # 노드 이름 설정
                node_name = fname
                # if channel:
                #     채널 이름이 감지되면 노드 이름을 채널 이름으로 변경
                #     node_name = CHANNEL_SUFFIXES.get(channel, channel.replace("_", " ").title())
                tex_node.SetValue("net.maxon.node.base.name", node_name)
                
                if not channel:
                    continue

                # 연결 로직
                tex_out = tex_node.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                
                if channel == "base_color":
                    if not connected_flags["base_color"]:
                        target = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_BASE_COLOR)
                        if target.IsValid():
                            redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_BASE_COLOR)
                            tex_out.Connect(target)
                            connected_flags["base_color"] = True
                
                if channel == "ao":
                    redshift_utils.set_colorspace_raw(tex_node)
                    mul_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_VECTOR_MULTIPLY)
                    created_nodes.append(mul_node)
                    if mul_node:
                        target = mul_node.GetInputs().FindChild(redshift_utils.PORT_RS_MATH_VECTOR_MULTIPLY_INPUT2)
                        if target.IsValid():
                            tex_out.Connect(target)

                elif channel == "metalness":
                    redshift_utils.set_colorspace_raw(tex_node)
                    if not connected_flags["metalness"]:
                        target = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_METALNESS)
                        if target.IsValid():
                            redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_METALNESS)
                            tex_out.Connect(target)
                            connected_flags["metalness"] = True
                
                elif channel == "refl_roughness":
                    redshift_utils.set_colorspace_raw(tex_node)
                    if not connected_flags["refl_roughness"]:
                        target = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_ROUGHNESS)
                        if target.IsValid():
                            redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_ROUGHNESS)
                            tex_out.Connect(target)
                            connected_flags["refl_roughness"] = True
                        
                elif channel == "refl_weight":
                    redshift_utils.set_colorspace_raw(tex_node)
                    if not connected_flags["refl_weight"]:
                        target = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_SPECULAR)
                        if target.IsValid():
                            redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_SPECULAR)
                            tex_out.Connect(target)
                            connected_flags["refl_weight"] = True
                
                elif channel == "glossiness":
                    redshift_utils.set_colorspace_raw(tex_node)
                    inv_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_INVERT)
                    created_nodes.append(inv_node)
                    if inv_node:
                        target = inv_node.GetInputs().FindChild(redshift_utils.PORT_RS_MATH_INVERT_INPUT)
                        if target.IsValid():
                            tex_out.Connect(target)

                elif channel == "opacity_color":
                    redshift_utils.set_colorspace_raw(tex_node)
                    if not connected_flags["opacity_color"]:
                        target = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_OPACITY)
                        if target.IsValid():
                            redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_OPACITY)
                            tex_out.Connect(target)
                            connected_flags["opacity_color"] = True
                
                elif channel == "emission_color":
                    if not connected_flags["emission_color"]:
                        target = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_EMISSION)
                        if target.IsValid():
                            redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_EMISSION)
                            tex_out.Connect(target)
                            connected_flags["emission_color"] = True
                        
                elif channel == "normal":
                    redshift_utils.set_colorspace_raw(tex_node)
                    # Create Bump Map Node (Type 1001 for Tangent Space Normal)
                    if not connected_flags["bump_input"] or connected_flags["bump_input"] == "Bump":
                        bump_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_BUMPMAP)
                        created_nodes.append(bump_node)
                        # bump_node.SetValue("net.maxon.node.base.name", "Normal")
                        
                        # Set Input Type to 1001 (Tangent-Space Normal)
                        bump_type_port = bump_node.GetInputs().FindChild(redshift_utils.PORT_RS_BUMP_TYPE)
                        if bump_type_port.IsValid():
                            bump_type_port.SetPortValue(1) # Normal
                            
                        # Connect Texture -> Bump Node
                        bump_in = bump_node.GetInputs().FindChild(redshift_utils.PORT_RS_BUMP_INPUT)
                        if bump_in.IsValid():
                            tex_out.Connect(bump_in)
                        
                        # Connect Bump Node -> Standard Material
                        bump_out = bump_node.GetOutputs().FindChild(redshift_utils.PORT_RS_BUMP_OUT)
                        std_bump_in = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_BUMP_INPUT)
                        if bump_out.IsValid() and std_bump_in.IsValid():
                            redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_BUMP_INPUT)
                            bump_out.Connect(std_bump_in)
                            connected_flags["bump_input"] = "Normal"
 
                elif channel == "bump":
                    redshift_utils.set_colorspace_raw(tex_node)
                    # Create Bump Map Node (Type 1000 for Height Field)
                    if not connected_flags["bump_input"]:
                        bump_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_BUMPMAP)
                        created_nodes.append(bump_node)
                        # bump_node.SetValue("net.maxon.node.base.name", "Bump")
                        
                        # Set Input Type to 1000
                        bump_type_port = bump_node.GetInputs().FindChild(redshift_utils.PORT_RS_BUMP_TYPE)
                        if bump_type_port.IsValid():
                            bump_type_port.SetPortValue(0) # Bump
                        
                        # Connect Texture -> Bump Node
                        bump_in = bump_node.GetInputs().FindChild(redshift_utils.PORT_RS_BUMP_INPUT)
                        if bump_in.IsValid():
                            tex_out.Connect(bump_in)
                        
                        # Connect Bump Node -> Standard Material
                        bump_out = bump_node.GetOutputs().FindChild(redshift_utils.PORT_RS_BUMP_OUT)
                        std_bump_in = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_BUMP_INPUT)
                        if bump_out.IsValid() and std_bump_in.IsValid():
                            redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_BUMP_INPUT)
                            bump_out.Connect(std_bump_in)
                            connected_flags["bump_input"] = "Bump"

                elif channel == "displacement":
                    redshift_utils.set_colorspace_raw(tex_node)
                    if not connected_flags["displacement"] and output_node:
                        disp_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_DISPLACEMENT)
                        created_nodes.append(disp_node)
                        disp_node.SetValue("net.maxon.node.base.name", "Displacement")
                        
                        # Connect Texture -> Displacement Node
                        disp_in = disp_node.GetInputs().FindChild(redshift_utils.PORT_RS_DISP_TEXMAP)
                        if disp_in.IsValid():
                            tex_out.Connect(disp_in)
                        
                        # Connect Displacement Node -> Output Node
                        disp_out = disp_node.GetOutputs().FindChild(redshift_utils.PORT_RS_DISP_OUT)
                        out_disp_in = output_node.GetInputs().FindChild(redshift_utils.PORT_RS_OUTPUT_DISPLACEMENT)
                        if disp_out.IsValid() and out_disp_in.IsValid():
                            redshift_utils.remove_connections(output_node, redshift_utils.PORT_RS_OUTPUT_DISPLACEMENT)
                            disp_out.Connect(out_disp_in)
                            connected_flags["displacement"] = True

            # 6. Select and Arrange
            maxon.GraphModelHelper.DeselectAll(graph, maxon.NODE_KIND.NODE)
            
            for node in created_nodes:
                if node.IsValid():
                    maxon.GraphModelHelper.SelectNode(node)
            
            if standard_mat.IsValid():
                maxon.GraphModelHelper.SelectNode(standard_mat)
            if output_node.IsValid():
                maxon.GraphModelHelper.SelectNode(output_node)

            transaction.Commit()
        
        c4d.CallCommand(465002311) # Arrange Selected Nodes
        c4d.EventAdd()
        
        return True

if __name__ == "__main__":
    icon_path = os.path.join(os.path.dirname(__file__), "IMfine_PBR_Texture_Setup.tif")
    bmp = c4d.bitmaps.BaseBitmap()
    if os.path.exists(icon_path):
        bmp.InitWith(icon_path)
    else:
        bmp = None

    c4d.plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str="Create PBR Material from Files...",
        info=0,
        icon=bmp,
        help="Loads texture files and automatically connects them to the material.",
        dat=CreatePBRMaterialCommand()
    )
