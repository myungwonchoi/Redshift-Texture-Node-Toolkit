import c4d
import maxon
import os
import sys
import shutil

# Add utils path
current_dir = os.path.dirname(__file__)
sub_dir = os.path.join(current_dir, "mw_utils")
if sub_dir not in sys.path:
    sys.path.append(sub_dir)

# Add dependencies path
dep_dir = os.path.join(current_dir, "dependencies")
if dep_dir not in sys.path:
    sys.path.append(dep_dir)

# Try to import PIL
PIL_ERROR_MSG = None
try:
    from PIL import Image
    print("PIL loaded successfully!")
except ImportError as e:
    Image = None
    PIL_ERROR_MSG = str(e)
    print(f"Failed to import PIL: {e}")
    print(f"Python Version: {sys.version}")
    print(f"sys.path: {sys.path}")

import redshift_utils

PLUGIN_ID = 1067303  # Temporary ID, needs to be distinct

def resize_and_strip_metadata(input_path, output_path):
    if not Image:
        raise ImportError(f"PIL library is not available. Error: {PIL_ERROR_MSG}")
    
    with Image.open(input_path) as img:
        # 1. Resize to 50%
        new_size = (img.width // 2, img.height // 2)
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # 2. Strip metadata by creating a new image
        # Using the same mode to preserve channels (e.g. RGBA)
        clean_img = Image.new(resized_img.mode, resized_img.size)
        clean_img.putdata(list(resized_img.getdata()))
        
        # 3. Save optimized
        # Determine format from extension or default to JPEG if original common formats
        # However, user example used "JPEG" explicitly. 
        # But we should respect original format if possible (ex: png, tif).
        # For this request, I'll follow user snippet's save style but adapt format.
        
        fmt = img.format if img.format else "JPEG"
        
        # Some formats don't support optimize/quality args the same way (e.g. PNG)
        # We will try simpler save first or specific logic.
        # User snippet: clean_img.save(output_path, "JPEG", optimize=True, quality=85)
        # I will infer format from extension for robustness.
        
        ext = os.path.splitext(output_path)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            clean_img.save(output_path, "JPEG", optimize=True, quality=85)
        elif ext in ['.png']:
             clean_img.save(output_path, "PNG", optimize=True)
        elif ext in ['.tif', '.tiff']:
             clean_img.save(output_path, "TIFF")
        else:
             clean_img.save(output_path)


def validate_selection(doc):
    # Reuse validation logic
    c4d.CallCommand(465002328) # Ensure Node Editor is open (optional but good context)
    mat = doc.GetActiveMaterial()
    if not mat:
        c4d.gui.MessageDialog("Please select a Redshift Node Material.")
        return None, None

    nodeMaterial = mat.GetNodeMaterialReference()
    if not nodeMaterial.HasSpace(redshift_utils.ID_RS_NODESPACE):
        c4d.gui.MessageDialog("Selected material is not a Redshift Node Material.")
        return None, None

    graph = nodeMaterial.GetGraph(redshift_utils.ID_RS_NODESPACE)
    if graph.IsNullValue():
        return None, None

    selected_nodes = []
    maxon.GraphModelHelper.GetSelectedNodes(graph, maxon.NODE_KIND.NODE, lambda node: selected_nodes.append(node) or True)

    texture_nodes = []
    for node in selected_nodes:
        if not node.IsValid(): continue
        asset_id = node.GetValue("net.maxon.node.attribute.assetid")[0]
        if asset_id == redshift_utils.ID_RS_TEXTURESAMPLER:
            texture_nodes.append(node)

    if not texture_nodes:
        c4d.gui.MessageDialog("Please select at least one Texture node.")
        return None, None

    return graph, texture_nodes

class ResizeTextureCommand(c4d.plugins.CommandData):
    def Execute(self, doc):
        # 0. Check PIL availability
        if not Image:
            c4d.gui.MessageDialog(f"PIL library failed to load.\n\nError: {PIL_ERROR_MSG}\n\nNote: Check if 'utils/PIL' is compatible with C4D's Python version.")
            return True

        # 1. Check Document Save State
        doc_path = doc.GetDocumentPath()
        if not doc_path:
            c4d.gui.MessageDialog("Please save the project first.")
            return True

        # 2. Validate Selection
        graph, texture_nodes = validate_selection(doc)
        if not graph:
            return True

        # 3. Prepare Texture Directory
        tex_folder = os.path.join(doc_path, "tex")
        if not os.path.exists(tex_folder):
            try:
                os.makedirs(tex_folder)
            except OSError as e:
                c4d.gui.MessageDialog(f"Failed to create 'tex' folder: {e}")
                return True

        processed_count = 0
        success_list = []
        fail_list = []
        
        with graph.BeginTransaction() as transaction:
            for node in texture_nodes:
                # Get current path
                path_port = node.GetInputs().FindChild(redshift_utils.PORT_RS_TEX_PATH).FindChild("path")
                if not path_port.IsValid():
                    continue
                
                current_path_val = path_port.GetPortValue()
                if current_path_val is None:
                    continue
                
                current_path = str(current_path_val)
                if isinstance(current_path_val, maxon.Url):
                    current_path = current_path_val.GetSystemPath()
                
                # 텍스처 파일 존재 여부 확인 및 경로 보정
                if not current_path or not os.path.isfile(current_path):
                    path_found = False
                    # 1. doc_path + current_path
                    if doc_path and current_path:
                        cand1 = os.path.join(doc_path, current_path)
                        if os.path.exists(cand1) and os.path.isfile(cand1):
                            current_path = cand1
                            path_found = True
                    
                    # 2. doc_path + "tex" + current_path
                    if not path_found and doc_path and current_path:
                        cand2 = os.path.join(doc_path, "tex", current_path)
                        if os.path.exists(cand2) and os.path.isfile(cand2):
                            current_path = cand2
                            path_found = True
                            
                    if not path_found:
                        print(f"    텍스처 파일이 존재하지 않거나 파일이 아닙니다: {current_path}")
                        fail_list.append(os.path.basename(current_path) if current_path else "Unknown Path")
                        continue

                # Prepare Target Path
                filename = os.path.basename(current_path)
                tex_folder_file = os.path.join(tex_folder, filename)

                # Copy original if it doesn't exist in tex folder
                # We check abspath to avoid copying if source is already the destination
                if not os.path.exists(tex_folder_file) or os.path.abspath(current_path) != os.path.abspath(tex_folder_file):
                    if not os.path.exists(tex_folder_file):
                        try:
                            shutil.copy2(current_path, tex_folder_file)
                            print(f"Copied original to: {tex_folder_file}")
                        except Exception as e:
                            print(f"Failed to copy original: {e}")

                # Use the local file as source for resizing if available
                source_path = tex_folder_file if os.path.exists(tex_folder_file) else current_path
                
                name, ext = os.path.splitext(filename)
                
                # Verify if already low res to avoid double shrinking? 
                # User asked to append "_Low".
                new_filename = f"{name}_Low{ext}"
                target_path = os.path.join(tex_folder, new_filename)

                # Resize Logic
                try:
                    should_resize = True
                    if os.path.exists(target_path):
                        # File exists, ask user to overwrite
                        # Note: This might be annoying if many files exist, but fulfills the specific request.
                        if c4d.gui.QuestionDialog(f"File '{new_filename}' already exists.\nOverwrite?"):
                             print(f"Overwriting: {new_filename}")
                             should_resize = True
                        else:
                             print(f"Using existing file: {new_filename}")
                             should_resize = False
                    
                    if should_resize:
                        if not os.path.exists(target_path) or should_resize: # Check again or just do it
                             print(f"Resizing: {filename} -> {new_filename}")
                             resize_and_strip_metadata(source_path, target_path)
                    
                    # Update Node Path
                    path_port.SetPortValue(target_path)
                    processed_count += 1
                    success_list.append(new_filename)
                    
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
                    fail_list.append(filename)
                    # Continue to next node even if one fails
        
            transaction.Commit()
        
        msg = ""
        if processed_count > 0:
            c4d.EventAdd()
            msg += f"Successfully resized/updated {processed_count} textures.\n\n"
        else:
            msg += "No textures were resized.\n\n"

        if success_list:
            msg += "[Changed Textures]\n" + "\n".join(success_list) + "\n\n"
        
        if fail_list:
             msg += "[Failed/Unchanged Textures]\n" + "\n".join(fail_list)
             
        c4d.gui.MessageDialog(msg)

        return True

if __name__ == "__main__":
    # Icon handling (reuses existing icon logic pattern, though we don't have a specific icon for this yet)
    # Using None for now or we could copy one.
    bmp = None

    c4d.plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str="Resize Texture Resolution...",
        info=0,
        icon=bmp,
        help="Reduces resolution of selected texture nodes images by 50%.",
        dat=ResizeTextureCommand()
    )
