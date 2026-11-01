import unittest

from llvmlite import binding

from codegen import LLVMCodeGenerator
from lexer import tokenize
from parser import Parser


class InterfaceCodeGenerationTests(unittest.TestCase):
    def compile_source(self, source):
        prog = Parser(tokenize(source)).parse_program()
        llvm_ir = LLVMCodeGenerator().generate_code(prog)
        module = binding.parse_assembly(llvm_ir)
        module.verify()
        return llvm_ir

    def test_generates_controls_click_queries_and_editable_text_queries(self):
        llvm_ir = self.compile_source(
            """
import os
val window = os.Make_Window("Demo")
val input = os.Make_Interface("label", "Demo", "search", (
    size = (240, 32),
    position = (10, 10),
    text = "Find",
    editable = true,
    text_color = "#112233",
    text_transparency = 0.75,
    background_color = "#FFFFFF",
    background_transparency = 0.8,
    font = "Segoe UI",
    text_size = 16
))
val button = os.Make_Interface("button", "Demo", "submit", (
    size = (90, 32),
    position = (10, 50),
    text = "Go"
))
val frame = os.Make_Interface("frame", "Demo", "panel", (
    size = (300, 120),
    position = (0, 90),
    layer = 3,
    background_color = "#EEEEEE",
    background_transparency = 0.5
))
val icon = os.Make_Interface("icon", "Demo", "logo", (
    size = (32, 32),
    position = (320, 10),
    icon = "assets/logo.png"
))
val icon_button = os.Make_Interface("button", "Demo", "icon-action", (
    size = (36, 36),
    position = (360, 10),
    icon = "assets/action.png"
))
val clicked = os.Interface_Clicked("Demo", "submit")
val value = os.Get_Interface_Text("Demo", "search")
os.Sleep(16)
while (true) : (
    if (os.Interface_Clicked("Demo", "submit")) : (
        val submitted = os.Get_Interface_Text("Demo", "search")
        free(submitted)
    )
    os.Sleep(16)
)
"""
        )

        self.assertIn("vamp_interface_click_flags", llvm_ir)
        self.assertIn("vamp_find_interface_parent", llvm_ir)
        self.assertIn("vamp_create_interface_control", llvm_ir)
        self.assertIn("vamp.interface.layer", llvm_ir)
        self.assertIn("SetWindowPos", llvm_ir)
        self.assertIn("RedrawWindow", llvm_ir)
        self.assertIn("SetBkColor", llvm_ir)
        self.assertIn("vamp.background.color", llvm_ir)
        self.assertIn("AlphaBlend", llvm_ir)
        self.assertIn("vamp.background.opacity", llvm_ir)
        self.assertGreater(
            llvm_ir.count("vamp_update_icon_background_brush"),
            1,
        )
        self.assertIn("GetWindowTextA", llvm_ir)

    def test_colored_background_uses_requested_alpha_without_white_blending(self):
        llvm_ir = self.compile_source(
            """
import os
val window = os.Make_Window("Demo")
val panel = os.Make_Interface("frame", "Demo", "panel", (
    size = (200, 100),
    position = (0, 0),
    background_color = "#336699",
    background_transparency = 0.5
))
"""
        )

        self.assertIn("i32 10053171", llvm_ir)
        self.assertIn("i32 131", llvm_ir)

    def test_background_transparency_maps_to_visible_opacity(self):
        llvm_ir = self.compile_source(
            """
import os
val window = os.Make_Window("Demo")
val panel = os.Make_Interface("frame", "Demo", "panel", (
    size = (200, 100),
    position = (0, 0),
    background_color = "#336699",
    background_transparency = 0.9
))
val faint = os.Make_Interface("frame", "Demo", "faint", (
    size = (200, 100),
    position = (0, 100),
    background_color = "#336699",
    background_transparency = 0.1
))
"""
        )

        self.assertIn("i32 29", llvm_ir)
        self.assertIn("i32 233", llvm_ir)

    def test_fractional_background_does_not_override_layer_paint_order(self):
        llvm_ir = self.compile_source(
            """
import os
val window = os.Make_Window("Demo")
val frame = os.Make_Interface("frame", "Demo", "panel", (
    size = (200, 100),
    position = (0, 0),
    layer = 1,
    background_color = "#336699",
    background_transparency = 0.7
))
val label = os.Make_Interface("label", "Demo", "title", (
    size = (100, 30),
    position = (10, 10),
    layer = 4,
    text = "Title"
))
"""
        )

        lines = llvm_ir.splitlines()
        style_pointer_index = next(
            index
            for index, line in enumerate(lines)
            if '"interface_creation_request"' in line and "i32 0, i32 2" in line
        )
        self.assertTrue(
            lines[style_pointer_index + 1].startswith(
                "  store i32 1140850688,"
            )
        )
        ex_style_pointer_index = next(
            index
            for index, line in enumerate(lines)
            if '"interface_creation_request"' in line and "i32 0, i32 8" in line
        )
        self.assertTrue(lines[ex_style_pointer_index + 1].startswith("  store i32 0,"))

    def test_layer_ordering_places_new_control_between_higher_and_lower_layers(self):
        llvm_ir = self.compile_source(
            """
import os
val window = os.Make_Window("Demo")
val frame = os.Make_Interface("frame", "Demo", "panel", (
    size = (200, 100),
    position = (0, 0),
    layer = 1,
    background_color = "#336699",
    background_transparency = 0.7
))
val label = os.Make_Interface("label", "Demo", "title", (
    size = (100, 30),
    position = (10, 10),
    layer = 4,
    text = "Title"
))
"""
        )

        self.assertIn('icmp sgt i32', llvm_ir)

    def test_buttons_with_custom_background_use_transparent_control_painting(self):
        llvm_ir = self.compile_source(
            """
import os
val window = os.Make_Window("Demo")
val styled = os.Make_Interface("button", "Demo", "styled", (
    size = (100, 40),
    position = (0, 0),
    text = "Styled",
    background_color = "#336699",
    background_transparency = 0.5
))
val native = os.Make_Interface("button", "Demo", "native", (
    size = (100, 40),
    position = (0, 50),
    text = "Native"
))
"""
        )

        self.assertIn('c"STATIC\\00"', llvm_ir)
        self.assertIn('c"BUTTON\\00"', llvm_ir)

    def test_rejects_properties_not_supported_by_interface_type(self):
        with self.assertRaisesRegex(SyntaxError, "not supported for interface type 'frame'"):
            self.compile_source(
                """
import os
val frame = os.Make_Interface("frame", "Demo", "panel", (
    size = (200, 100),
    position = (0, 0),
    text = "not supported"
))
"""
            )

    def test_rejects_transparency_outside_range(self):
        with self.assertRaisesRegex(ValueError, "text_transparency.*0.0 to 1.0"):
            self.compile_source(
                """
import os
val label = os.Make_Interface("label", "Demo", "title", (
    size = (200, 30),
    position = (0, 0),
    text = "Title",
    text_transparency = 1.1
))
"""
            )

    def test_layer_must_be_an_integer(self):
        with self.assertRaisesRegex(TypeError, "property 'layer' must be an int"):
            self.compile_source(
                """
import os
val frame = os.Make_Interface("frame", "Demo", "panel", (
    size = (200, 100),
    position = (0, 0),
    layer = 1.5
))
"""
            )

    def test_text_query_requires_editable_label(self):
        with self.assertRaisesRegex(TypeError, "not an editable text field"):
            self.compile_source(
                """
import os
val button = os.Make_Interface("button", "Demo", "submit", (
    size = (90, 32),
    position = (0, 0),
    text = "Go"
))
val value = os.Get_Interface_Text("Demo", "submit")
"""
            )

    def test_rejects_queries_for_undeclared_interfaces(self):
        with self.assertRaisesRegex(NameError, "is not declared"):
            self.compile_source(
                """
import os
val clicked = os.Interface_Clicked("Demo", "missing")
"""
            )


if __name__ == "__main__":
    unittest.main()
