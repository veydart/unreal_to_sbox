import unreal
import os
import struct

def extract_tga_alpha(base_tga_path):
    if not os.path.exists(base_tga_path):
        return None
        
    mask_path = base_tga_path.replace(".tga", "_mask.tga")
    if os.path.exists(mask_path):
        return os.path.basename(mask_path)
        
    try:
        with open(base_tga_path, "rb") as f:
            header = f.read(18)
            h = struct.unpack("<BBB5sHHHHBB", header)
            id_len, image_type, width, height, bpp, img_desc = h[0], h[2], h[6], h[7], h[8], h[9]
            
            if image_type != 2 or bpp != 32:
                return None
                
            if id_len > 0: f.read(id_len)
            pixels = f.read(width * height * 4)
            
        if len(pixels) != width * height * 4:
            return None
            
        a_channel = bytes(memoryview(pixels)[3::4])
        
        with open(mask_path, "wb") as out_f:
            out_desc = img_desc & 0xF0
            out_header = struct.pack("<BBB5sHHHHBB", 0, 0, 3, b'\x00\x00\x00\x00\x00', 0, 0, width, height, 8, out_desc)
            out_f.write(out_header)
            out_f.write(a_channel)
            
        return os.path.basename(mask_path)
    except Exception as e:
        return None

def split_packed_tga(base_tga_path):
    if not os.path.exists(base_tga_path):
        return None, None, None
        
    ao_path = base_tga_path.replace(".tga", "_ao.tga")
    rough_path = base_tga_path.replace(".tga", "_rough.tga")
    metal_path = base_tga_path.replace(".tga", "_metal.tga")

    try:
        with open(base_tga_path, "rb") as f:
            header = f.read(18)
            h = struct.unpack("<BBB5sHHHHBB", header)
            id_len, image_type, width, height, bpp, img_desc = h[0], h[2], h[6], h[7], h[8], h[9]
            if image_type != 2 or bpp < 24: 
                return None, None, None
            if id_len > 0: f.read(id_len)
            
            pixels = f.read(width * height * (bpp // 8))
            
        mv = memoryview(pixels)
        b_bytes = bpp // 8
        
        filename_lower = os.path.basename(base_tga_path).lower()
        if "_rma" in filename_lower or "_rsa" in filename_lower:
            ao_channel    = bytes(mv[0::b_bytes]) 
            metal_channel = bytes(mv[1::b_bytes]) 
            rough_channel = bytes(mv[2::b_bytes]) 
        else:
            ao_channel    = bytes(mv[2::b_bytes]) 
            rough_channel = bytes(mv[1::b_bytes]) 
            metal_channel = bytes(mv[0::b_bytes]) 
        
        out_desc = img_desc & 0xF0
        out_header = struct.pack("<BBB5sHHHHBB", 0, 0, 3, b'\x00\x00\x00\x00\x00', 0, 0, width, height, 8, out_desc)
        
        with open(ao_path, "wb") as f_ao:
            f_ao.write(out_header)
            f_ao.write(ao_channel)
        with open(rough_path, "wb") as f_rough:
            f_rough.write(out_header)
            f_rough.write(rough_channel)
        with open(metal_path, "wb") as f_metal:
            f_metal.write(out_header)
            f_metal.write(metal_channel)
            
        # Clean up original packed TGA to avoid asset clutter in s&box
        try:
            os.remove(base_tga_path)
        except OSError:
            pass
            
        return os.path.basename(ao_path), os.path.basename(rough_path), os.path.basename(metal_path)
    except Exception as e:
        return None, None, None

def export_selected_to_sbox(export_dir):
    selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()
    if not selected_assets:
        unreal.log_warning("No assets selected for export.")
        return

    exportable_assets = [
        a for a in selected_assets 
        if isinstance(a, (unreal.StaticMesh, unreal.SkeletalMesh))
    ]

    if not exportable_assets:
        unreal.log_warning("No StaticMeshes or SkeletalMeshes selected.")
        return

    for asset in exportable_assets:
        asset_name = asset.get_name()
        
        package_name = str(asset.get_path_name()).split('.')[0]
        rel_dir = os.path.dirname(package_name.replace("/Game/", ""))
        final_dir = os.path.normpath(os.path.join(export_dir, rel_dir))
        os.makedirs(final_dir, exist_ok=True)
        
        fbx_filename = f"{asset_name.lower()}.fbx"
        fbx_path = os.path.join(final_dir, fbx_filename)

        task = unreal.AssetExportTask()
        task.object = asset
        task.filename = fbx_path
        task.automated = True
        task.prompt = False
        task.options = unreal.FbxExportOption()
        task.options.vertex_color = True
        task.options.collision = False
        task.options.level_of_detail = False
        unreal.Exporter.run_asset_export_task(task)
        unreal.log(f"Exported FBX: {fbx_path}")
        
        material_remaps = []
        
        materials = []
        if isinstance(asset, unreal.StaticMesh):
            static_mats = asset.get_editor_property("static_materials")
            for static_mat in static_mats:
                if static_mat.material_interface:
                    materials.append(static_mat.material_interface)
        elif isinstance(asset, unreal.SkeletalMesh):
            for skel_mat in asset.materials:
                if skel_mat.material_interface:
                    materials.append(skel_mat.material_interface)
                    
        unreal.log(f"Found {len(materials)} materials on {asset_name}")

        for mat_interface in materials:
            original_mat_name = mat_interface.get_name()
            vmat_filename_str = original_mat_name.lower()
            
            mat_package = str(mat_interface.get_path_name()).split('.')[0]
            mat_rel_dir = os.path.dirname(mat_package.replace("/Game/", ""))
            vmat_rel_path = f"{mat_rel_dir}/{vmat_filename_str}.vmat".replace("\\", "/")
            
            material_remaps.append((original_mat_name, vmat_rel_path))
            
            export_material_and_textures(mat_interface, export_dir, vmat_filename_str)

        generate_vmdl(final_dir, asset_name.lower(), fbx_filename, material_remaps, rel_dir)


def export_material_and_textures(mat_interface, output_dir, vmat_filename_str):
    mat_package = str(mat_interface.get_path_name()).split('.')[0]
    mat_rel_dir = os.path.dirname(mat_package.replace("/Game/", ""))
    mat_final_dir = os.path.normpath(os.path.join(output_dir, mat_rel_dir))
    os.makedirs(mat_final_dir, exist_ok=True)
    vmat_path = os.path.join(mat_final_dir, f"{vmat_filename_str}.vmat")
    
    texture_paths = {
        "Color": None, "Normal": None, "Rough": None, "Metal": None,
        "Translucency": None, "AO": None, "Height": None
    }
    
    uv_scale = [1.000, 1.000]
    color_tint = [1.000, 1.000, 1.000, 0.000]
    
    package_name = str(mat_interface.get_path_name()).split('.')[0]
    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
    options = unreal.AssetRegistryDependencyOptions()
    options.include_hard_package_references = True
    options.include_soft_package_references = False
    
    registry_deps = asset_registry.get_dependencies(package_name, options)
    deps = set(str(d) for d in registry_deps)
    
    is_transparent = False
    
    if isinstance(mat_interface, unreal.MaterialInstance):
        try:
            tex_params = mat_interface.get_editor_property("texture_parameter_values")
            for t_item in tex_params:
                t_val = t_item.get_editor_property("parameter_value")
                p_name_info = t_item.get_editor_property("parameter_info")
                if t_val and p_name_info:
                    p_name = str(p_name_info.get_editor_property("name")).lower()
                    
                    tex_package = str(t_val.get_path_name()).split('.')[0]
                    tex_rel_dir = os.path.dirname(tex_package.replace("/Game/", ""))
                    tex_filename = f"{t_val.get_name().lower()}.tga"
                    tex_rel_path = f"{tex_rel_dir}/{tex_filename}".replace("\\", "/")
                    
                    if p_name in ["basecolor", "base color", "albedo", "diffuse", "color"]:
                        texture_paths["Color"] = tex_rel_path
                    elif p_name in ["normal", "normalmap", "normal map", "nrm"]:
                        texture_paths["Normal"] = tex_rel_path
                    elif p_name in ["height", "depth", "displacement", "bump", "disp"]:
                        texture_paths["Height"] = tex_rel_path
                    elif p_name in ["roughness", "rough", "rma", "orm", "mask", "ao", "ambientocclusion"]:
                        texture_paths["Rough"] = tex_rel_path
                        texture_paths["Metal"] = tex_rel_path
                        texture_paths["AO"] = tex_rel_path
                    elif p_name in ["metallic", "metalness", "metal"]:
                        texture_paths["Metal"] = tex_rel_path
                    elif p_name in ["opacity", "opacitymask", "alpha", "translucency"]:
                        texture_paths["Translucency"] = tex_rel_path
                    else:
                        if not texture_paths["Color"] and ("color" in p_name or "albedo" in p_name or "diffuse" in p_name or "base" in p_name):
                            texture_paths["Color"] = tex_rel_path
                        elif not texture_paths["Normal"] and ("normal" in p_name or "nrm" in p_name):
                            texture_paths["Normal"] = tex_rel_path
                        elif not texture_paths["Height"] and ("height" in p_name or "disp" in p_name or "depth" in p_name or "_h" in tex_filename):
                            texture_paths["Height"] = tex_rel_path
                        elif not texture_paths["Rough"] and ("rough" in p_name or "rma" in p_name or "orm" in p_name or "mask" in p_name or "ao" in p_name):
                            texture_paths["Rough"] = tex_rel_path
                            texture_paths["Metal"] = tex_rel_path
                            texture_paths["AO"] = tex_rel_path
                        elif not texture_paths["Translucency"] and ("opacity" in p_name or "alpha" in p_name or "trans" in p_name):
                            texture_paths["Translucency"] = tex_rel_path
                            
            scalar_params = mat_interface.get_editor_property("scalar_parameter_values")
            for s_item in scalar_params:
                s_val = s_item.get_editor_property("parameter_value")
                p_name_info = s_item.get_editor_property("parameter_info")
                if p_name_info:
                    p_name = str(p_name_info.get_editor_property("name")).lower()
                    if ("tiling" in p_name or "uv_scale" in p_name or "uvscale" in p_name or "scale_u" in p_name or "scale_v" in p_name or "coords" in p_name or "coord" in p_name):
                        if "detail" not in p_name and "micro" not in p_name and "macro" not in p_name and "noise" not in p_name:
                            if "u" in p_name or "x" in p_name:
                                uv_scale[0] = float(s_val)
                            elif "v" in p_name or "y" in p_name:
                                uv_scale[1] = float(s_val)
                            elif "tiling" in p_name or "scale" in p_name:
                                uv_scale[0] = float(s_val)
                                uv_scale[1] = float(s_val)
                            
            vector_params = mat_interface.get_editor_property("vector_parameter_values")
            for v_item in vector_params:
                v_val = v_item.get_editor_property("parameter_value")
                p_name_info = v_item.get_editor_property("parameter_info")
                if v_val and p_name_info:
                    p_name = str(p_name_info.get_editor_property("name")).lower()
                    if ("tiling" in p_name or "uv_scale" in p_name or "scale" in p_name or "coords" in p_name or "coord" in p_name):
                        if "micro" not in p_name and "macro" not in p_name and "noise" not in p_name:
                            try:
                                uv_scale[0] = float(v_val.r)
                                uv_scale[1] = float(v_val.g)
                            except AttributeError:
                                uv_scale[0] = float(v_val.x)
                                uv_scale[1] = float(v_val.y)
                    elif ("tint" in p_name or "color" in p_name) and "base" not in p_name and "ambient" not in p_name:
                        try:
                            color_tint[0] = float(v_val.r)
                            color_tint[1] = float(v_val.g)
                            color_tint[2] = float(v_val.b)
                            color_tint[3] = float(v_val.a)
                        except AttributeError:
                            color_tint[0] = float(v_val.x)
                            color_tint[1] = float(v_val.y)
                            color_tint[2] = float(v_val.z)
                            color_tint[3] = 1.0
                            
            if "bark" in package_name.lower():
                if abs(uv_scale[0] - 1.0) < 0.01 and abs(uv_scale[1] - 1.0) < 0.01:
                    uv_scale[0] = 3.0
                    uv_scale[1] = 3.0
                        
        except Exception as e:
            unreal.log_warning(f"Failed to read MaterialInstance textures: {e}")

    is_masked = False
    is_translucent = False
    try:
        blend_mode = mat_interface.get_blend_mode()
        if blend_mode == unreal.BlendMode.BLEND_MASKED:
            is_masked = True
        elif blend_mode == unreal.BlendMode.BLEND_TRANSLUCENT:
            is_translucent = True
    except Exception:
        pass
        
    is_transparent = is_masked or is_translucent

    unreal.log(f"Found {len(deps)} asset dependencies for material {vmat_filename_str}. Masked: {is_masked}, Translucent: {is_translucent}")
    
    # Second pass: ensure missing dependencies mapped and textures actually exported
    for dep_path in deps:
        asset = unreal.EditorAssetLibrary.load_asset(dep_path)
        if isinstance(asset, unreal.Texture):
            tex_name = asset.get_name().lower()
            tex_filename = f"{tex_name}.tga"
            
            tex_package = str(asset.get_path_name()).split('.')[0]
            tex_rel_dir = os.path.dirname(tex_package.replace("/Game/", ""))
            tex_rel_path = f"{tex_rel_dir}/{tex_filename}".replace("\\", "/")
            
            tex_final_dir = os.path.normpath(os.path.join(output_dir, tex_rel_dir))
            os.makedirs(tex_final_dir, exist_ok=True)
            tex_path = os.path.join(tex_final_dir, tex_filename)
            
            if not os.path.exists(tex_path):
                task = unreal.AssetExportTask()
                task.object = asset
                task.filename = tex_path
                task.automated = True
                task.prompt = False
                task.exporter = unreal.TextureExporterTGA()
                unreal.Exporter.run_asset_export_task(task)
            
            comp_settings = asset.get_editor_property("compression_settings")
            is_srgb = asset.get_editor_property("srgb")
            
            if not texture_paths["Normal"] and ("norm" in tex_name or "_nrm" in tex_name or tex_name.endswith("_n") or comp_settings == unreal.TextureCompressionSettings.TC_NORMALMAP):
                texture_paths["Normal"] = tex_rel_path
            elif not texture_paths["Height"] and ("disp" in tex_name or "height" in tex_name or "_h" in tex_name or tex_name.endswith("_h")):
                texture_paths["Height"] = tex_rel_path
            elif not texture_paths["Rough"] and ("_mrp" in tex_name or "orm" in tex_name or "mask" in tex_name or "_rma" in tex_name or comp_settings == unreal.TextureCompressionSettings.TC_MASKS):
                texture_paths["Rough"] = tex_rel_path
                texture_paths["Metal"] = tex_rel_path
                texture_paths["AO"] = tex_rel_path
            elif not texture_paths["Rough"] and ("rough" in tex_name or tex_name.endswith("_r") or tex_name.endswith("_rsa")):
                texture_paths["Rough"] = tex_rel_path
                texture_paths["AO"] = tex_rel_path
            elif not texture_paths["Metal"] and ("metal" in tex_name or tex_name.endswith("_m")):
                texture_paths["Metal"] = tex_rel_path
            elif not texture_paths["Color"] and ("color" in tex_name or "diffuse" in tex_name or "albedo" in tex_name or "alb" in tex_name or tex_name.endswith("_d") or tex_name.endswith("_c")):
                texture_paths["Color"] = tex_rel_path
            elif not texture_paths["Color"] and is_srgb:
                texture_paths["Color"] = tex_rel_path

    vmat_content = f"""// THIS FILE IS AUTO-GENERATED
Layer0
{{
    shader "complex.vfx"

    //---- PBR ----
    F_SPECULAR 1

    //---- Color ----
    g_flModelTintAmount "1.000"
    g_vColorTint "[{color_tint[0]:.6f} {color_tint[1]:.6f} {color_tint[2]:.6f} {color_tint[3]:.6f}]"

    //---- Texture Coordinates ----
    g_vTexCoordOffset "[0.000 0.000]"
    g_vTexCoordScale "[{uv_scale[0]:.3f} {uv_scale[1]:.3f}]"
    
"""
    if is_masked:
        vmat_content += '    F_ALPHA_TEST 1\n'
        vmat_content += '    g_flAlphaTestReference "0.500"\n'
        vmat_content += '    F_RENDER_BACKFACES 1\n'
    elif is_translucent:
        vmat_content += '    F_TRANSLUCENT 1\n'
        vmat_content += '    F_RENDER_BACKFACES 1\n'

    if texture_paths["Normal"]:
        if not is_transparent:
            vmat_content += '    F_ENABLE_NORMAL_SELF_SHADOW 1\n'
            vmat_content += '    F_SCALE_NORMAL_MAP 1\n'
        
    if texture_paths.get("Height") and not is_transparent:
        vmat_content += '    F_PARALLAX_OCCLUSION 1\n'

    if texture_paths["Color"]:
        vmat_content += f'    TextureColor "{texture_paths["Color"]}"\n'
        
    if is_transparent:
         trans_tex_name = texture_paths["Translucency"] if texture_paths["Translucency"] else texture_paths["Color"]
         if trans_tex_name:
             base_tga_path = os.path.normpath(os.path.join(output_dir, trans_tex_name.replace("/", os.sep)))
             mask_filename = extract_tga_alpha(base_tga_path)
             if mask_filename:
                 mask_rel_path = trans_tex_name.replace(os.path.basename(trans_tex_name), mask_filename)
                 vmat_content += f'    TextureTranslucency "{mask_rel_path}"\n'
             else:
                 vmat_content += f'    TextureTranslucency "{trans_tex_name}"\n'

    vmat_content += "\n    //---- Normal ----\n"
    if texture_paths["Normal"]:
        if not is_transparent:
            vmat_content += '    g_flLightRangeForSelfShadowNormals "0.707"\n'
            vmat_content += '    g_flNormalMapScaleFactor "1.000"\n'
        vmat_content += f'    TextureNormal "{texture_paths["Normal"]}"\n'

    rough_override = texture_paths["Rough"]
    metal_override = texture_paths["Metal"]
    ao_override = texture_paths["AO"]
    
    if texture_paths["Rough"] and texture_paths["Rough"] == texture_paths["Metal"]:
        packed_tga_path = os.path.normpath(os.path.join(output_dir, texture_paths["Rough"].replace("/", os.sep)))
        ao_f, rough_f, metal_f = split_packed_tga(packed_tga_path)
        if rough_f:
            rough_override = texture_paths["Rough"].replace(os.path.basename(texture_paths["Rough"]), rough_f)
            metal_override = texture_paths["Metal"].replace(os.path.basename(texture_paths["Metal"]), metal_f)
            if not texture_paths["AO"] or texture_paths["Rough"] == texture_paths["AO"]:
                ao_override = texture_paths["AO"].replace(os.path.basename(texture_paths["AO"]), ao_f)

    vmat_content += "\n    //---- Roughness ----\n"
    if rough_override:
        vmat_content += f'    TextureRoughness "{rough_override}"\n'

    vmat_content += "\n    //---- Metalness ----\n"
    if metal_override:
        vmat_content += f'    TextureMetalness "{metal_override}"\n'

    vmat_content += "\n    //---- Ambient Occlusion ----\n"
    if ao_override:
        vmat_content += '    g_flAmbientOcclusionDirectDiffuse "0.000"\n'
        vmat_content += '    g_flAmbientOcclusionDirectSpecular "0.000"\n'
        vmat_content += f'    TextureAmbientOcclusion "{ao_override}"\n'

    vmat_content += "\n    //---- Depth / Parallax ----\n"
    if texture_paths.get("Height") and not is_transparent:
        vmat_content += '    g_flHeightMapScale "0.030"\n'
        vmat_content += '    g_nLODThreshold "4"\n'
        vmat_content += '    g_nMaxSamples "32"\n'
        vmat_content += '    g_nMinSamples "8"\n'
        vmat_content += f'    TextureHeight "{texture_paths["Height"]}"\n'
        
    vmat_content += "}\n"
    with open(vmat_path, "w", encoding="utf-8") as f:
        f.write(vmat_content)
    
    unreal.log(f"Generated VMAT: {vmat_path}")


def generate_vmdl(target_dir, model_name, fbx_filename, material_remaps, rel_dir):
    vmdl_path = os.path.join(target_dir, f"{model_name}.vmdl")
    
    remaps_str = ""
    for ue_mat_name, sbox_vmat_path in material_remaps:
        remaps_str += f"""                            {{
                                from = "{ue_mat_name}.vmat"
                                to = "{sbox_vmat_path}"
                            }},\n"""

    fbx_rel_path = f"{rel_dir}/{fbx_filename}".replace("\\", "/")

    vmdl_content = f"""<!-- kv3 encoding:text:version{{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d}} format:modeldoc29:version{{3cec427c-1b0e-4d48-a90a-0436f33a6041}} -->
{{
    rootNode = 
    {{
        _class = "RootNode"
        children = 
        [
            {{
                _class = "RenderMeshList"
                children = 
                [
                    {{
                        _class = "RenderMeshFile"
                        filename = "{fbx_rel_path}"
                        import_translation = [ 0.0, 0.0, 0.0 ]
                        import_rotation = [ 0.0, 0.0, 0.0 ]
                        import_scale = 0.393701
                        align_origin_x_type = "None"
                        align_origin_y_type = "None"
                        align_origin_z_type = "None"
                        parent_bone = ""
                        import_filter = 
                        {{
                            exclude_by_default = false
                            exception_list = [  ]
                        }}
                    }},
                ]
            }},
            {{
                _class = "PhysicsShapeList"
                children = 
                [
                    {{
                        _class = "PhysicsHullFromRender"
                        name = "generated_hull"
                        parent_bone = ""
                        surface_prop = "default"
                        collision_tags = "solid"
                        faceMergeAngle = 20.0
                        maxHullVertices = 32
                    }},
                ]
            }},
            {{
                _class = "MaterialGroupList"
                children = 
                [
                    {{
                        _class = "DefaultMaterialGroup"
                        remaps = 
                        [
{remaps_str}                        ]
                        use_global_default = false
                        global_default_material = ""
                    }},
                ]
            }},
        ]
        model_archetype = ""
        primary_associated_entity = ""
        anim_graph_name = ""
        base_model_name = ""
    }}
}}
"""
    with open(vmdl_path, "w", encoding="utf-8") as f:
        f.write(vmdl_content)
    
    unreal.log(f"Generated VMDL: {vmdl_path}")
