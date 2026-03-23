# 🌳 Unreal Engine 5 to s&box Exporter (Complete Guide)

This huge and complex Python script (`export_to_sbox.py`) automatically ports any selected objects (Static Meshes, Skeletal Meshes) from Unreal Engine 5 directly into your s&box / Source 2 project, creating 100% game-ready graphics with a single click.

---

## 🔥 What exactly does the script do "under the hood"?

1. **Folder Mirroring**: If your tree was located in the `/Game/Nature/Trees/Pine_01/` folder, the script will physically recreate this exact beautiful folder hierarchy inside your `s&box/Assets/...` project. No more dumping hundreds of images into one messy folder!
2. **Geometry Export**: Silent and error-free export of `.fbx` geometry with all smoothing groups, LOD options, and tangents intact.
3. **.vmdl (ModelDoc) Generation**: Automatic assembly of the Source 2 model, generating basic physical collision hulls, and linking materials natively through Remaps.
4. **Smart PBR Parsing**:
   - Automatically calculates UV Scaling from the Unreal material graph (reading `Texture Coord X` and `Y` scaling scalar parameters natively on the fly).
   - Perfectly "slices" heavy `_rma` / `_rsa` packed textures into 3 separate lightweight black-and-white masks (AO, Roughness, Metallic) and **immediately deletes the junk originals behind it**, freeing up tens of megabytes of redundant hard drive space per tree.
5. **Shader Magic (`complex.vfx`)**:
   - Automatically maps and enables **Alpha Test** transparency and two-sided geometry rendering (`F_RENDER_BACKFACES`) for all leaves.
   - For opaque surfaces like bark, it automatically enables 3D-relief (**Parallax Occlusion Mapping**) with an optimized depth metric of `g_flHeightMapScale 0.030`.
   - Automatically enables micro-normal map scaling and self-shadowing (which would normally completely break leaf transparency, but the script mathematically "sees" the transparency and actively blocks these checkboxes for leaves!).

---

## 🛠️ Setup (One-Time)

1. Open Unreal Engine. Go to **Edit -> Plugins**.
2. Search for `Python` and ensure that the **Python Editor Script Plugin** is enabled.
3. In the same Plugins window, find **Editor Scripting Utilities** and ensure it is also enabled. Restart the engine if prompted.
4. Verify that your core python file is saved at: `H:\test\unreal_to_sandbox\export_to_sbox.py`.

---

## 🖥️ Variant 1: Usage without a UI Button (Via Console)

This method is highly suitable if you want to perform a quick one-off export, debugging, or if you prefer not to create custom UI buttons.

1. In the bottom Unreal Engine window (**Content Browser**), select one or multiple trees (`Static Mesh`) that you want to export.
2. At the very bottom left corner of the Unreal Editor window, find the `Cmd` console input line. Click on the `Cmd` text and switch its execution mode to **Python**.
3. Copy the following code, paste it into this console window, and press **Enter**:

```python
import sys
# Inject path to system scope so UE finds our local package
if r"h:\test\unreal_to_sandbox" not in sys.path:
    sys.path.append(r"h:\test\unreal_to_sandbox")

import export_to_sbox
import importlib
importlib.reload(export_to_sbox)

# Path to the base Assets folder in your s&box project! Replace if it changes.
export_to_sbox.export_selected_to_sbox(r"H:\sbox\my_project_2\Assets")
```

👉 As soon as you press Enter, the script will "freeze" for a second, and lines of successful exports will fly through the engine log.

---

## 🚀 Variant 2: Usage with a UI Button (Pro Choice)

This is the best and most convenient production method. We will permanently "bake" this script into the native Unreal Engine UI. You will be able to export objects with a single standard right-click.

1. In the **Content Browser** window, right-click on any empty gray area.
2. Select **Editor Utilities -> Editor Utility Blueprint**.
3. In the parent class selection window that appears, select **AssetActionUtility**. 
4. A new blue blueprint file will appear. Name it `BP_SboxExporter` and double-click to open it's logic graph.
5. In the opened programming window on the left, under the **Functions** section, click the **+** (Plus) button to create a new blueprint function.
6. Name this function **`Export To Sbox`**. (This is exactly what our button will be called when you right-click on assets!).
7. On the right in the **Details** panel, find the **"Call In Editor"** checkbox and **ENABLE** it. This is the most crucial step allowing UI rendering.
8. Return to the center graph. From the initial red node `Export To Sbox`, drag the white execution wire to the right and release it on empty space.
9. In the search bar, type exactly `Execute Python Command` and select this green node.
10. Click on the spawned green node. On the right in the Details section, find the large multi-line text field **Command** and paste the exact following block of code there:

```python
import sys
if r"h:\test\unreal_to_sandbox" not in sys.path:
    sys.path.append(r"h:\test\unreal_to_sandbox")

import export_to_sbox
import importlib
importlib.reload(export_to_sbox)

export_to_sbox.export_selected_to_sbox(r"H:\sbox\my_project_2\Assets")
```

11. Click the **Compile** checkmark at the top left and the **Save** floppy disk button. The warning icons should disappear. The blueprint can now be permanently closed.

### 🎉 How to use it:
1. Select any number of tree models simultaneously in the Unreal Engine window.
2. **Right-Click** on any of them.
3. In the massive list of the context menu, locate the **Scripted Asset Actions** sub-menu.
4. Select **`Export To Sbox`**.

That's it! The script will instantly execute the entire multi-step PBR export hierarchy and geometry mirroring pipeline directly to your hard drive! Brilliant automation architecture complete.
