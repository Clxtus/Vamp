from llvmlite import ir
from parser import ArrayAccessNode, ArrayAssignmentNode, ArrayLiteralNode, AssignmentNode, BinaryOpNode, ClassDeclarationNode, ClassInstanceDeclarationNode, ComparisonNode, DictionaryAccessNode, DictionaryLiteralNode, ForLoopNode, IfNode, LiteralNode, LibraryImportNode, ImportFileNode, LibraryCallNode, MallocNode, MethodCallNode, VariableAccessNode, VariableDeclarationNode, WhileLoopNode, WindowConfigNode, WindowPointNode, WindowSizeNode

class ArrayLiteralValue:
    def __init__(self, elements, element_type):
        self.elements = elements
        self.element_type = element_type

class ArrayReferenceValue:
    def __init__(self, pointer, element_type, length):
        self.pointer = pointer
        self.element_type = element_type
        self.length = length

class DictionaryLiteralValue:
    def __init__(self, entries):
        self.entries = entries

class ClassInstanceValue:
    def __init__(self, pointer):
        self.pointer = pointer

class PointerValue:
    def __init__(self, pointer, element_type):
        self.pointer = pointer
        self.element_type = element_type

class LLVMCodeGenerator:
    def __init__(self):
        self.module = ir.Module(name="vamp_module")
        self.builder = None
        self.variable_pointers = {}
        self.type_information = {}
        self.constant_variables = set()
        self.array_information = {}
        self.dictionary_information = {}
        self.class_definitions = {}
        self.class_methods = {}
        self.emitted_class_methods = set()
        self.imported_libraries = set()
        self.string_literal_count = 0

        self.int32_type = ir.IntType(32)
        self.int64_type = ir.IntType(64)
        self.int16_type = ir.IntType(16)
        self.float_type = ir.FloatType()
        self.bool_type = ir.IntType(1)
        self.char_pointer_type = ir.IntType(8).as_pointer()

        printf_type = ir.FunctionType(self.int32_type, [self.char_pointer_type], var_arg=True)
        self.printf_function = ir.Function(self.module, printf_type, name="printf")

        snprintf_type = ir.FunctionType(self.int32_type, [self.char_pointer_type, self.int32_type, self.char_pointer_type], var_arg=True)
        self.snprintf_function = ir.Function(self.module, snprintf_type, name="snprintf")

        malloc_type = ir.FunctionType(self.char_pointer_type, [self.int64_type])
        self.malloc_function = ir.Function(self.module, malloc_type, name="malloc")

        strlen_type = ir.FunctionType(self.int32_type, [self.char_pointer_type])
        self.strlen_function = ir.Function(self.module, strlen_type, name="strlen")

        strcpy_type = ir.FunctionType(self.char_pointer_type, [self.char_pointer_type, self.char_pointer_type])
        self.strcpy_function = ir.Function(self.module, strcpy_type, name="strcpy")

        strcat_type = ir.FunctionType(self.char_pointer_type, [self.char_pointer_type, self.char_pointer_type])
        self.strcat_function = ir.Function(self.module, strcat_type, name="strcat")

        atoi_type = ir.FunctionType(self.int32_type, [self.char_pointer_type])
        self.atoi_function = ir.Function(self.module, atoi_type, name="atoi")

        atof_type = ir.FunctionType(ir.DoubleType(), [self.char_pointer_type])
        self.atof_function = ir.Function(self.module, atof_type, name="atof")

        strcmp_type = ir.FunctionType(self.int32_type, [self.char_pointer_type, self.char_pointer_type])
        self.strcmp_function = ir.Function(self.module, strcmp_type, name="strcmp")

        exit_type = ir.FunctionType(ir.VoidType(), [self.int32_type])
        self.exit_function = ir.Function(self.module, exit_type, name="exit")

        free_type = ir.FunctionType(ir.VoidType(), [self.char_pointer_type])
        self.free_function = ir.Function(self.module, free_type, name="free")

        create_directory_type = ir.FunctionType(self.int32_type, [self.char_pointer_type, self.char_pointer_type, self.char_pointer_type])
        self.create_directory_function = ir.Function(self.module, create_directory_type, name="SHCreateDirectoryExA")

        file_attributes_type = ir.FunctionType(self.int32_type, [self.char_pointer_type])
        self.get_file_attributes_function = ir.Function(
            self.module,
            file_attributes_type,
            name="GetFileAttributesA",
        )

        find_first_file_type = ir.FunctionType(
            self.char_pointer_type,
            [self.char_pointer_type, self.char_pointer_type],
        )
        self.find_first_file_function = ir.Function(
            self.module,
            find_first_file_type,
            name="FindFirstFileA",
        )

        find_next_file_type = ir.FunctionType(
            self.int32_type,
            [self.char_pointer_type, self.char_pointer_type],
        )
        self.find_next_file_function = ir.Function(
            self.module,
            find_next_file_type,
            name="FindNextFileA",
        )

        find_close_type = ir.FunctionType(self.int32_type, [self.char_pointer_type])
        self.find_close_function = ir.Function(
            self.module,
            find_close_type,
            name="FindClose",
        )

        get_last_error_type = ir.FunctionType(self.int32_type, [])
        self.get_last_error_function = ir.Function(
            self.module,
            get_last_error_type,
            name="GetLastError",
        )

        shell_execute_type = ir.FunctionType(
            self.char_pointer_type,
            [
                self.char_pointer_type,
                self.char_pointer_type,
                self.char_pointer_type,
                self.char_pointer_type,
                self.char_pointer_type,
                self.int32_type,
            ],
        )
        self.shell_execute_function = ir.Function(
            self.module,
            shell_execute_type,
            name="ShellExecuteA",
        )

        snapshot_type = ir.FunctionType(self.char_pointer_type, [self.int32_type, self.int32_type])
        self.create_process_snapshot_function = ir.Function(
            self.module,
            snapshot_type,
            name="CreateToolhelp32Snapshot",
        )
        process_entry_type = ir.FunctionType(
            self.int32_type,
            [self.char_pointer_type, self.char_pointer_type],
        )
        self.process32_first_function = ir.Function(
            self.module,
            process_entry_type,
            name="Process32First",
        )
        self.process32_next_function = ir.Function(
            self.module,
            process_entry_type,
            name="Process32Next",
        )
        self.open_process_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.char_pointer_type,
                [self.int32_type, self.int32_type, self.int32_type],
            ),
            name="OpenProcess",
        )
        self.terminate_process_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type, self.int32_type]),
            name="TerminateProcess",
        )
        self.close_handle_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="CloseHandle",
        )
        self.get_module_handle_function = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.char_pointer_type]),
            name="GetModuleHandleA",
        )
        self.sleep_function = ir.Function(
            self.module,
            ir.FunctionType(ir.VoidType(), [self.int32_type]),
            name="Sleep",
        )
        self.multi_byte_to_wide_char_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [
                    self.int32_type,
                    self.int32_type,
                    self.char_pointer_type,
                    self.int32_type,
                    self.int16_type.as_pointer(),
                    self.int32_type,
                ],
            ),
            name="MultiByteToWideChar",
        )
        self.gdiplus_startup_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [self.int64_type.as_pointer(), self.char_pointer_type, self.char_pointer_type],
            ),
            name="GdiplusStartup",
        )
        self.gdiplus_load_image_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [self.int16_type.as_pointer(), self.char_pointer_type.as_pointer()],
            ),
            name="GdipLoadImageFromFile",
        )
        self.gdiplus_create_icon_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [self.char_pointer_type, self.char_pointer_type.as_pointer()],
            ),
            name="GdipCreateHICONFromBitmap",
        )
        self.gdiplus_dispose_image_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="GdipDisposeImage",
        )
        self.gdiplus_shutdown_function = ir.Function(
            self.module,
            ir.FunctionType(ir.VoidType(), [self.int64_type]),
            name="GdiplusShutdown",
        )
        self.send_message_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int64_type,
                [self.char_pointer_type, self.int32_type, self.int64_type, self.int64_type],
            ),
            name="SendMessageA",
        )
        self.get_system_metrics_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.int32_type]),
            name="GetSystemMetrics",
        )
        self.destroy_icon_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="DestroyIcon",
        )
        self.create_solid_brush_function = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.int32_type]),
            name="CreateSolidBrush",
        )
        self.create_compatible_dc_function = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.char_pointer_type]),
            name="CreateCompatibleDC",
        )
        self.create_compatible_bitmap_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.char_pointer_type,
                [self.char_pointer_type, self.int32_type, self.int32_type],
            ),
            name="CreateCompatibleBitmap",
        )
        self.select_object_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.char_pointer_type,
                [self.char_pointer_type, self.char_pointer_type],
            ),
            name="SelectObject",
        )
        self.set_pixel_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [
                    self.char_pointer_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                ],
            ),
            name="SetPixelV",
        )
        self.get_pixel_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [self.char_pointer_type, self.int32_type, self.int32_type],
            ),
            name="GetPixel",
        )
        self.alpha_blend_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [
                    self.char_pointer_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                    self.char_pointer_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                ],
            ),
            name="AlphaBlend",
        )
        self.get_client_rect_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [self.char_pointer_type, self.char_pointer_type],
            ),
            name="GetClientRect",
        )
        self.delete_object_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="DeleteObject",
        )
        self.delete_dc_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="DeleteDC",
        )
        self.get_stock_object_function = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.int32_type]),
            name="GetStockObject",
        )
        self.set_text_color_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type, self.int32_type]),
            name="SetTextColor",
        )
        self.set_background_color_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type, self.int32_type]),
            name="SetBkColor",
        )
        self.set_background_mode_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type, self.int32_type]),
            name="SetBkMode",
        )
        self.get_property_function = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.char_pointer_type, self.char_pointer_type]),
            name="GetPropA",
        )
        self.set_property_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type, self.char_pointer_type, self.char_pointer_type]),
            name="SetPropA",
        )
        self.create_font_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.char_pointer_type,
                [
                    self.int32_type, self.int32_type, self.int32_type, self.int32_type,
                    self.int32_type, self.int32_type, self.int32_type, self.int32_type,
                    self.int32_type, self.int32_type, self.int32_type, self.int32_type,
                    self.int32_type, self.char_pointer_type,
                ],
            ),
            name="CreateFontA",
        )
        self.load_image_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.char_pointer_type,
                [
                    self.char_pointer_type, self.char_pointer_type, self.int32_type,
                    self.int32_type, self.int32_type, self.int32_type,
                ],
            ),
            name="LoadImageA",
        )
        self.active_windows_global = None
        self.interface_clicked_global = None
        self.interface_ids = {}
        self.interface_id_count = 0
        self.interface_message_pump_function = None
        self.compare_case_insensitive_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type, self.char_pointer_type]),
            name="lstrcmpiA",
        )
        self.get_window_thread_process_id_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [self.char_pointer_type, self.int32_type.as_pointer()],
            ),
            name="GetWindowThreadProcessId",
        )
        self.get_current_process_id_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, []),
            name="GetCurrentProcessId",
        )
        self.process_operation_function = None
        self.window_runtime_functions = None
        self.window_operation_function = None
        self.window_icon_function = None
        self.interface_creation_function = None
        self.interface_request_type = None
        self.interface_parent_function = None

        self.register_window_class_function = ir.Function(
            self.module,
            ir.FunctionType(self.int16_type, [self.char_pointer_type]),
            name="RegisterClassExA",
        )
        self.create_window_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.char_pointer_type,
                [
                    self.int32_type,
                    self.char_pointer_type,
                    self.char_pointer_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                    self.char_pointer_type,
                    self.char_pointer_type,
                    self.char_pointer_type,
                    self.char_pointer_type,
                ],
            ),
            name="CreateWindowExA",
        )
        self.destroy_window_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="DestroyWindow",
        )
        self.set_last_error_function = ir.Function(
            self.module,
            ir.FunctionType(ir.VoidType(), [self.int32_type]),
            name="SetLastError",
        )
        self.get_window_function = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.char_pointer_type, self.int32_type]),
            name="GetWindow",
        )
        self.set_window_pos_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [
                    self.char_pointer_type,
                    self.char_pointer_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                ],
            ),
            name="SetWindowPos",
        )
        self.find_window_function = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.char_pointer_type, self.char_pointer_type]),
            name="FindWindowA",
        )
        self.get_dialog_item_function = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.char_pointer_type, self.int32_type]),
            name="GetDlgItem",
        )
        self.get_window_text_length_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="GetWindowTextLengthA",
        )
        self.show_window_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type, self.int32_type]),
            name="ShowWindow",
        )
        self.update_window_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="UpdateWindow",
        )
        self.redraw_window_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [
                    self.char_pointer_type,
                    self.char_pointer_type,
                    self.char_pointer_type,
                    self.int32_type,
                ],
            ),
            name="RedrawWindow",
        )
        self.get_message_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [self.char_pointer_type, self.char_pointer_type, self.int32_type, self.int32_type],
            ),
            name="GetMessageA",
        )
        self.peek_message_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [
                    self.char_pointer_type,
                    self.char_pointer_type,
                    self.int32_type,
                    self.int32_type,
                    self.int32_type,
                ],
            ),
            name="PeekMessageA",
        )
        self.translate_message_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="TranslateMessage",
        )
        self.dispatch_message_function = ir.Function(
            self.module,
            ir.FunctionType(self.int64_type, [self.char_pointer_type]),
            name="DispatchMessageA",
        )
        self.default_window_proc_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int64_type,
                [self.char_pointer_type, self.int32_type, self.int64_type, self.int64_type],
            ),
            name="DefWindowProcA",
        )
        self.post_quit_message_function = ir.Function(
            self.module,
            ir.FunctionType(ir.VoidType(), [self.int32_type]),
            name="PostQuitMessage",
        )
        self.create_event_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.char_pointer_type,
                [self.char_pointer_type, self.int32_type, self.int32_type, self.char_pointer_type],
            ),
            name="CreateEventA",
        )
        self.set_event_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="SetEvent",
        )
        self.wait_for_single_object_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type, self.int32_type]),
            name="WaitForSingleObject",
        )
        self.create_thread_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.char_pointer_type,
                [
                    self.char_pointer_type,
                    self.int64_type,
                    self.char_pointer_type,
                    self.char_pointer_type,
                    self.int32_type,
                    self.char_pointer_type,
                ],
            ),
            name="CreateThread",
        )
        self.enum_windows_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type, self.int64_type]),
            name="EnumWindows",
        )
        self.is_window_visible_function = ir.Function(
            self.module,
            ir.FunctionType(self.int32_type, [self.char_pointer_type]),
            name="IsWindowVisible",
        )
        self.get_window_text_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [self.char_pointer_type, self.char_pointer_type, self.int32_type],
            ),
            name="GetWindowTextA",
        )
        self.post_message_function = ir.Function(
            self.module,
            ir.FunctionType(
                self.int32_type,
                [self.char_pointer_type, self.int32_type, self.int64_type, self.int64_type],
            ),
            name="PostMessageA",
        )
        full_path_type = ir.FunctionType(
            self.int32_type,
            [
                self.char_pointer_type,
                self.int32_type,
                self.char_pointer_type,
                self.char_pointer_type.as_pointer(),
            ],
        )
        self.get_full_path_name_function = ir.Function(
            self.module,
            full_path_type,
            name="GetFullPathNameA",
        )

        self.file_operation_type = ir.LiteralStructType([
            self.char_pointer_type,
            self.int32_type,
            self.char_pointer_type,
            self.char_pointer_type,
            ir.IntType(16),
            self.int32_type,
            self.char_pointer_type,
            self.char_pointer_type,
        ])
        file_operation_function_type = ir.FunctionType(
            self.int32_type,
            [self.file_operation_type.as_pointer()],
        )
        self.file_operation_function = ir.Function(
            self.module,
            file_operation_function_type,
            name="SHFileOperationA",
        )

    def generate_code(self, program):
        class_declarations = [
            stmt for stmt in program
            if isinstance(stmt, ClassDeclarationNode)
        ]
        for decl in class_declarations:
            self.register_class_tree(decl)
        for decl in class_declarations:
            self.declare_class_methods(decl)

        main_type = ir.FunctionType(self.int32_type, [])
        main_function = ir.Function(self.module, main_type, name="main")
        entry_block = main_function.append_basic_block(name="entry")
        self.builder = ir.IRBuilder(entry_block)

        for stmt in program:
            self.visit(stmt)

        undeclared_interfaces = [
            key
            for key, info in self.interface_ids.items()
            if not info["declared"]
        ]
        if undeclared_interfaces:
            window_title, interface_name = undeclared_interfaces[0]
            raise NameError(
                f"Interface '{interface_name}' for window '{window_title}' is not declared"
            )

        if self.active_windows_global is not None:
            check_block = main_function.append_basic_block(name="check_open_windows")
            wait_block = main_function.append_basic_block(name="wait_for_windows")
            finish_block = main_function.append_basic_block(name="windows_closed")
            self.builder.branch(check_block)
            self.builder.position_at_end(check_block)
            active_windows = self.builder.atomic_rmw(
                "add",
                self.active_windows_global,
                ir.Constant(self.int32_type, 0),
                "acquire",
                name="active_window_count",
            )
            windows_remain = self.builder.icmp_signed(
                ">",
                active_windows,
                ir.Constant(self.int32_type, 0),
            )
            self.builder.cbranch(windows_remain, wait_block, finish_block)
            self.builder.position_at_end(wait_block)
            self.emit_interface_message_pump()
            self.builder.call(self.sleep_function, [ir.Constant(self.int32_type, 100)])
            self.builder.branch(check_block)
            self.builder.position_at_end(finish_block)

        self.builder.ret(ir.Constant(self.int32_type, 0))
        return str(self.module)

    def constant_string_pointer(self, value):
        string_content = value + "\0"
        string_constant = ir.Constant(
            ir.ArrayType(ir.IntType(8), len(string_content)),
            bytearray(string_content.encode("utf-8")),
        )
        self.string_literal_count += 1
        string_global = ir.GlobalVariable(
            self.module,
            string_constant.type,
            name=f".str_{self.string_literal_count}",
        )
        string_global.linkage = "internal"
        string_global.initializer = string_constant
        return string_global.bitcast(self.char_pointer_type)

    def visit(self, node):
        visitor_name = f"visit_{type(node).__name__}"
        visitor = getattr(self, visitor_name, self.visit_unhandled_node)
        return visitor(node)

    def visit_unhandled_node(self, node):
        raise NotImplementedError(f"No visit_{type(node).__name__} method defined.")

    def visit_LibraryImportNode(self, node):
        self.imported_libraries.add(node.library_name)

    def visit_ImportFileNode(self, node):
        pass

    def visit_ClassDeclarationNode(self, node):
        self.emit_class_methods(node)

    def visit_ClassInstanceDeclarationNode(self, node):
        instance_value, instance_type = self.visit(node.initializer)
        if not isinstance(instance_value, ClassInstanceValue):
            raise TypeError(f"'{node.instance_name}' must be initialized with a class instance")
        self.variable_pointers[node.instance_name] = instance_value.pointer
        self.type_information[node.instance_name] = instance_type
        self.array_information.pop(node.instance_name, None)
        self.dictionary_information.pop(node.instance_name, None)

    def allocate_bytes(self, size, name=None):
        if size.type == self.int32_type:
            size = self.builder.zext(size, self.int64_type, name="allocation_size")
        elif size.type != self.int64_type:
            raise TypeError(f"Allocation size must be an integer, got {size.type}")
        if name is None:
            return self.builder.call(self.malloc_function, [size])
        return self.builder.call(self.malloc_function, [size], name=name)

    def visit_MallocNode(self, node):
        cnt, count_type = self.visit(node.count)
        if count_type != "int":
            raise TypeError(f"malloc element count must be int, got {count_type}")
        if isinstance(node.count, LiteralNode) and node.count.value <= 0:
            raise ValueError("malloc element count must be greater than zero")

        fn = self.builder.function
        valid_count = self.builder.icmp_signed(
            ">",
            cnt,
            ir.Constant(self.int32_type, 0),
            name="malloc_valid_count",
        )
        allocation_block = fn.append_basic_block(name="malloc_allocate")
        error_block = fn.append_basic_block(name="malloc_invalid_count")
        self.builder.cbranch(valid_count, allocation_block, error_block)

        self.builder.position_at_end(error_block)
        error_message = self.visit_LiteralNode(
            LiteralNode("str", "Error: malloc element count must be greater than zero\n")
        )[0]
        self.builder.call(self.printf_function, [error_message])
        self.builder.call(self.exit_function, [ir.Constant(self.int32_type, 1)])
        self.builder.unreachable()

        self.builder.position_at_end(allocation_block)
        elem_ty = self.llvm_type_for(node.element_type)
        element_size = {
            "int": 4,
            "float": 4,
            "bool": 1,
            "str": 8,
        }[node.element_type]
        count_64 = self.builder.zext(cnt, self.int64_type, name="malloc_element_count")
        byte_count = self.builder.mul(
            count_64,
            ir.Constant(self.int64_type, element_size),
            name="malloc_byte_count",
        )
        raw_pointer = self.allocate_bytes(byte_count, name="malloc_raw_pointer")
        allocation_failed = self.builder.icmp_unsigned(
            "==",
            raw_pointer,
            ir.Constant(self.char_pointer_type, None),
            name="malloc_failed",
        )
        failed_block = fn.append_basic_block(name="malloc_failed")
        success_block = fn.append_basic_block(name="malloc_success")
        self.builder.cbranch(allocation_failed, failed_block, success_block)

        self.builder.position_at_end(failed_block)
        error_message = self.visit_LiteralNode(
            LiteralNode("str", "Error: malloc could not allocate memory\n")
        )[0]
        self.builder.call(self.printf_function, [error_message])
        self.builder.call(self.exit_function, [ir.Constant(self.int32_type, 1)])
        self.builder.unreachable()

        self.builder.position_at_end(success_block)
        typed_pointer = self.builder.bitcast(
            raw_pointer,
            elem_ty.as_pointer(),
            name="malloc_typed_pointer",
        )
        return PointerValue(typed_pointer, node.element_type), f"pointer:{node.element_type}"

    def visit_AssignmentNode(self, node):
        variable_pointer = self.variable_pointers.get(node.variable_name)
        if node.operator == "=":
            value, val_ty = self.visit(node.expression)
            if variable_pointer is None:
                if not isinstance(value, ClassInstanceValue):
                    raise NameError(f"Variable '{node.variable_name}' is not declared")
                self.variable_pointers[node.variable_name] = value.pointer
                self.type_information[node.variable_name] = val_ty
                self.array_information.pop(node.variable_name, None)
                self.dictionary_information.pop(node.variable_name, None)
                return
            if isinstance(value, PointerValue):
                value = value.pointer
        else:
            if variable_pointer is None:
                raise NameError(f"Variable '{node.variable_name}' is not declared")
            value, val_ty = self.visit(
                BinaryOpNode(
                    VariableAccessNode(node.variable_name),
                    node.operator[0],
                    node.expression,
                )
            )

        if node.variable_name in self.constant_variables:
            raise TypeError(f"Cannot assign to constant '{node.variable_name}'")
        want_ty = self.type_information[node.variable_name]
        if want_ty not in ("int", "float", "bool", "str") and not want_ty.startswith("pointer:"):
            raise TypeError(f"Assignment to values of type '{want_ty}' is not supported")
        if val_ty != want_ty:
            raise TypeError(
                f"Cannot assign {val_ty} to variable '{node.variable_name}' of type {want_ty}"
            )
        self.builder.store(value, variable_pointer)

    def register_class_tree(self, node, parent_name=None):
        qualified_name = f"{parent_name}.{node.class_name}" if parent_name else node.class_name
        if qualified_name in self.class_definitions:
            raise SyntaxError(f"Class '{qualified_name}' is already declared")

        fields = {}
        llvm_field_types = []
        for field_index, (field_name, field_ty, is_constant) in enumerate(node.fields):
            if field_name in fields:
                raise SyntaxError(f"Duplicate field '{field_name}' in class '{qualified_name}'")
            fields[field_name] = (field_index, field_ty, is_constant)
            llvm_field_types.append(self.llvm_type_for(field_ty))

        nested_classes = {
            nested.class_name: f"{qualified_name}.{nested.class_name}"
            for nested in node.nested_classes
        }
        self.class_definitions[qualified_name] = {
            "fields": fields,
            "field_order": [field_name for field_name, _, _ in node.fields],
            "llvm_type": ir.LiteralStructType(llvm_field_types),
            "nested_classes": nested_classes,
            "methods": node.methods,
        }

        for nested_class in node.nested_classes:
            self.register_class_tree(nested_class, qualified_name)

    def declare_class_methods(self, node, parent_name=None):
        qualified_name = f"{parent_name}.{node.class_name}" if parent_name else node.class_name
        for meth in node.methods:
            method_key = (qualified_name, meth.function_name)
            if method_key in self.class_methods:
                raise SyntaxError(
                    f"Method '{meth.function_name}' is already declared on '{qualified_name}'"
                )

            parameter_types = [self.llvm_type_for(parameter_type) for _, parameter_type in meth.parameters]
            function_type = ir.FunctionType(
                self.llvm_type_for(meth.return_type),
                [self.class_definitions[qualified_name]["llvm_type"].as_pointer(), *parameter_types],
            )
            function_name = f"{qualified_name.replace('.', '__')}__{meth.function_name}"
            fn = ir.Function(self.module, function_type, name=function_name)
            self.class_methods[method_key] = {
                "function": fn,
                "return_type": meth.return_type,
                "parameters": meth.parameters,
                "declaration": meth,
            }

        for nested_class in node.nested_classes:
            self.declare_class_methods(nested_class, qualified_name)

    def emit_class_methods(self, node, parent_name=None):
        qualified_name = f"{parent_name}.{node.class_name}" if parent_name else node.class_name
        for meth in node.methods:
            method_key = (qualified_name, meth.function_name)
            if method_key in self.emitted_class_methods:
                continue
            self.emitted_class_methods.add(method_key)
            method_information = self.class_methods[method_key]
            previous_builder = self.builder
            previous_variable_pointers = self.variable_pointers.copy()
            previous_type_information = self.type_information.copy()
            previous_array_information = self.array_information.copy()
            previous_dictionary_information = self.dictionary_information.copy()
            previous_constant_variables = self.constant_variables.copy()

            fn = method_information["function"]
            entry_block = fn.append_basic_block(name="entry")
            self.builder = ir.IRBuilder(entry_block)
            self.variable_pointers["self"] = fn.args[0]
            self.type_information["self"] = f"class:{qualified_name}"

            for argument_index, (parameter_name, parameter_type) in enumerate(meth.parameters, start=1):
                parameter_pointer = self.builder.alloca(self.llvm_type_for(parameter_type), name=parameter_name)
                self.builder.store(fn.args[argument_index], parameter_pointer)
                self.variable_pointers[parameter_name] = parameter_pointer
                self.type_information[parameter_name] = parameter_type

            for stmt in meth.body:
                self.visit(stmt)

            if not self.builder.block.is_terminated:
                if isinstance(fn.function_type.return_type, ir.VoidType):
                    raise SyntaxError(
                        f"Method '{qualified_name}.{meth.function_name}' must end with 'return : void'"
                    )
                raise SyntaxError(
                    f"Method '{qualified_name}.{meth.function_name}' must return a value"
                )

            self.builder = previous_builder
            self.variable_pointers = previous_variable_pointers
            self.type_information = previous_type_information
            self.array_information = previous_array_information
            self.dictionary_information = previous_dictionary_information
            self.constant_variables = previous_constant_variables

        for nested_class in node.nested_classes:
            self.emit_class_methods(nested_class, qualified_name)

    def get_window_icon_function(self):
        if self.window_icon_function is not None:
            return self.window_icon_function

        fn = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.char_pointer_type]),
            name="vamp_load_window_icon",
        )
        fn.linkage = "internal"
        fn.args[0].name = "icon_path"
        entry = fn.append_basic_block(name="entry")
        startup_failed = fn.append_basic_block(name="startup_failed")
        startup_succeeded = fn.append_basic_block(name="startup_succeeded")
        conversion_failed = fn.append_basic_block(name="conversion_failed")
        conversion_succeeded = fn.append_basic_block(name="conversion_succeeded")
        image_failed = fn.append_basic_block(name="image_failed")
        image_loaded = fn.append_basic_block(name="image_loaded")
        icon_created = fn.append_basic_block(name="icon_created")
        icon_failed = fn.append_basic_block(name="icon_failed")
        builder = ir.IRBuilder(entry)

        startup_input_type = ir.LiteralStructType(
            [self.int32_type, self.char_pointer_type, self.int32_type, self.int32_type]
        )
        startup_input = builder.alloca(startup_input_type, name="gdiplus_startup_input")
        startup_input_fields = [
            ir.Constant(self.int32_type, 1),
            ir.Constant(self.char_pointer_type, None),
            ir.Constant(self.int32_type, 0),
            ir.Constant(self.int32_type, 0),
        ]
        for idx, value in enumerate(startup_input_fields):
            field_pointer = builder.gep(
                startup_input,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)],
            )
            builder.store(value, field_pointer)

        startup_token = builder.alloca(self.int64_type, name="gdiplus_token")
        startup_status = builder.call(
            self.gdiplus_startup_function,
            [
                startup_token,
                builder.bitcast(startup_input, self.char_pointer_type),
                ir.Constant(self.char_pointer_type, None),
            ],
        )
        startup_ok = builder.icmp_signed(
            "==",
            startup_status,
            ir.Constant(self.int32_type, 0),
        )
        builder.cbranch(startup_ok, startup_succeeded, startup_failed)

        builder.position_at_end(startup_failed)
        builder.ret(ir.Constant(self.char_pointer_type, None))

        builder.position_at_end(startup_succeeded)
        icon_path_wide = builder.alloca(
            ir.ArrayType(self.int16_type, 32768),
            name="icon_path_wide",
        )
        icon_path_wide_pointer = builder.gep(
            icon_path_wide,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 0)],
        )
        wide_character_count = builder.call(
            self.multi_byte_to_wide_char_function,
            [
                ir.Constant(self.int32_type, 65001),
                ir.Constant(self.int32_type, 0),
                fn.args[0],
                ir.Constant(self.int32_type, -1),
                icon_path_wide_pointer,
                ir.Constant(self.int32_type, 32768),
            ],
        )
        path_converted = builder.icmp_signed(
            ">",
            wide_character_count,
            ir.Constant(self.int32_type, 0),
        )
        builder.cbranch(path_converted, conversion_succeeded, conversion_failed)

        builder.position_at_end(conversion_failed)
        startup_token_value = builder.load(startup_token)
        builder.call(self.gdiplus_shutdown_function, [startup_token_value])
        builder.ret(ir.Constant(self.char_pointer_type, None))

        builder.position_at_end(conversion_succeeded)
        image_pointer = builder.alloca(self.char_pointer_type, name="gdiplus_image")
        load_status = builder.call(
            self.gdiplus_load_image_function,
            [icon_path_wide_pointer, image_pointer],
        )
        image_loaded_ok = builder.icmp_signed(
            "==",
            load_status,
            ir.Constant(self.int32_type, 0),
        )
        builder.cbranch(image_loaded_ok, image_loaded, image_failed)

        builder.position_at_end(image_failed)
        failed_token = builder.load(startup_token)
        builder.call(self.gdiplus_shutdown_function, [failed_token])
        builder.ret(ir.Constant(self.char_pointer_type, None))

        builder.position_at_end(image_loaded)
        image = builder.load(image_pointer)
        icon_pointer = builder.alloca(self.char_pointer_type, name="window_icon")
        icon_status = builder.call(
            self.gdiplus_create_icon_function,
            [image, icon_pointer],
        )
        icon_ok = builder.icmp_signed(
            "==",
            icon_status,
            ir.Constant(self.int32_type, 0),
        )
        builder.cbranch(icon_ok, icon_created, icon_failed)

        builder.position_at_end(icon_failed)
        failed_image = builder.load(image_pointer)
        builder.call(self.gdiplus_dispose_image_function, [failed_image])
        failed_token = builder.load(startup_token)
        builder.call(self.gdiplus_shutdown_function, [failed_token])
        builder.ret(ir.Constant(self.char_pointer_type, None))

        builder.position_at_end(icon_created)
        loaded_icon = builder.load(icon_pointer)
        image_to_dispose = builder.load(image_pointer)
        builder.call(self.gdiplus_dispose_image_function, [image_to_dispose])
        token_to_shutdown = builder.load(startup_token)
        builder.call(self.gdiplus_shutdown_function, [token_to_shutdown])
        builder.ret(loaded_icon)

        self.window_icon_function = fn
        return fn

    def emit_interface_icon_background_brush_function(self):
        fn = ir.Function(
            self.module,
            ir.FunctionType(
                self.char_pointer_type,
                [self.char_pointer_type, self.char_pointer_type, self.int32_type, self.int32_type],
            ),
            name="vamp_update_icon_background_brush",
        )
        fn.linkage = "internal"
        entry = fn.append_basic_block(name="entry")
        delete_previous = fn.append_basic_block(name="delete_previous_icon_brush")
        create_brush = fn.append_basic_block(name="create_icon_mask_brush")
        builder = ir.IRBuilder(entry)
        control, device_context, x_position, y_position = fn.args
        property_name = self.constant_string_pointer("vamp.icon.background.brush")
        previous_brush = builder.call(
            self.get_property_function,
            [control, property_name],
        )
        has_previous_brush = builder.icmp_unsigned(
            "!=",
            previous_brush,
            ir.Constant(self.char_pointer_type, None),
        )
        builder.cbranch(has_previous_brush, delete_previous, create_brush)

        builder.position_at_end(delete_previous)
        builder.call(self.delete_object_function, [previous_brush])
        builder.branch(create_brush)

        builder.position_at_end(create_brush)
        background_color = builder.call(
            self.get_pixel_function,
            [device_context, x_position, y_position],
        )
        brush = builder.call(
            self.create_solid_brush_function,
            [background_color],
        )
        builder.call(
            self.set_property_function,
            [control, property_name, brush],
        )
        builder.ret(brush)
        return fn

    def get_window_runtime_functions(self):
        if self.window_runtime_functions is not None:
            return self.window_runtime_functions

        pointer_type = self.char_pointer_type
        interface_creation_function = ir.Function(
            self.module,
            ir.FunctionType(
                pointer_type,
                [pointer_type, self.get_interface_request_type().as_pointer()],
            ),
            name="vamp_create_interface_control",
        )
        interface_creation_function.linkage = "internal"
        interface_creation_function.args[0].name = "parent_window"
        interface_creation_function.args[1].name = "request"
        self.interface_creation_function = interface_creation_function
        icon_background_brush_function = (
            self.emit_interface_icon_background_brush_function()
        )

        window_proc_type = ir.FunctionType(
            self.int64_type,
            [pointer_type, self.int32_type, self.int64_type, self.int64_type],
        )
        window_proc = ir.Function(
            self.module,
            window_proc_type,
            name="vamp_window_proc",
        )
        window_proc.linkage = "internal"
        window_proc.args[0].name = "window"
        window_proc.args[1].name = "message"
        window_proc.args[2].name = "wparam"
        window_proc.args[3].name = "lparam"

        self.interface_clicked_global = ir.GlobalVariable(
            self.module,
            ir.ArrayType(self.int32_type, 0x10000),
            name="vamp_interface_click_flags",
        )
        self.interface_clicked_global.initializer = ir.Constant(
            self.interface_clicked_global.type.pointee,
            None,
        )

        entry = window_proc.append_basic_block(name="entry")
        destroy_block = window_proc.append_basic_block(name="destroy")
        interface_check_block = window_proc.append_basic_block(name="interface_check")
        interface_create_block = window_proc.append_basic_block(name="interface_create")
        color_check_block = window_proc.append_basic_block(name="color_check")
        color_block = window_proc.append_basic_block(name="control_color")
        command_check_block = window_proc.append_basic_block(name="command_check")
        command_click_block = window_proc.append_basic_block(name="command_click")
        default_block = window_proc.append_basic_block(name="default")
        proc_builder = ir.IRBuilder(entry)
        is_destroy = proc_builder.icmp_signed(
            "==",
            window_proc.args[1],
            ir.Constant(self.int32_type, 2),
        )
        proc_builder.cbranch(is_destroy, destroy_block, interface_check_block)
        proc_builder.position_at_end(destroy_block)
        proc_builder.call(
            self.post_quit_message_function,
            [ir.Constant(self.int32_type, 0)],
        )
        proc_builder.ret(ir.Constant(self.int64_type, 0))

        proc_builder.position_at_end(interface_check_block)
        is_interface_create = proc_builder.icmp_signed(
            "==",
            window_proc.args[1],
            ir.Constant(self.int32_type, 0x8001),
        )
        proc_builder.cbranch(
            is_interface_create,
            interface_create_block,
            color_check_block,
        )

        proc_builder.position_at_end(interface_create_block)
        interface_request = proc_builder.inttoptr(
            window_proc.args[3],
            self.get_interface_request_type().as_pointer(),
        )
        created_control = proc_builder.call(
            interface_creation_function,
            [window_proc.args[0], interface_request],
        )
        proc_builder.ret(proc_builder.ptrtoint(created_control, self.int64_type))

        proc_builder.position_at_end(color_check_block)
        msg = window_proc.args[1]
        is_control_color = None
        for color_message in (0x0132, 0x0133, 0x0135, 0x0138):
            matches = proc_builder.icmp_signed(
                "==",
                msg,
                ir.Constant(self.int32_type, color_message),
            )
            is_control_color = matches if is_control_color is None else proc_builder.or_(
                is_control_color,
                matches,
            )
        proc_builder.cbranch(is_control_color, color_block, command_check_block)

        proc_builder.position_at_end(color_block)
        control_window = proc_builder.inttoptr(window_proc.args[3], self.char_pointer_type)
        device_context = proc_builder.inttoptr(window_proc.args[2], self.char_pointer_type)
        text_color = proc_builder.call(
            self.get_property_function,
            [control_window, self.constant_string_pointer("vamp.text.color")],
        )
        background_brush = proc_builder.call(
            self.get_property_function,
            [control_window, self.constant_string_pointer("vamp.background.brush")],
        )
        background_opacity = proc_builder.call(
            self.get_property_function,
            [control_window, self.constant_string_pointer("vamp.background.opacity")],
        )
        background_color = proc_builder.call(
            self.get_property_function,
            [control_window, self.constant_string_pointer("vamp.background.color")],
        )
        background_transparent = proc_builder.call(
            self.get_property_function,
            [control_window, self.constant_string_pointer("vamp.background.transparent")],
        )
        is_icon_control = proc_builder.call(
            self.get_property_function,
            [control_window, self.constant_string_pointer("vamp.interface.icon")],
        )
        has_color_properties = proc_builder.or_(
            proc_builder.icmp_unsigned(
                "!=",
                text_color,
                ir.Constant(self.char_pointer_type, None),
            ),
            proc_builder.or_(
                proc_builder.icmp_unsigned(
                    "!=",
                    background_brush,
                    ir.Constant(self.char_pointer_type, None),
                ),
                proc_builder.icmp_unsigned(
                    "!=",
                    background_transparent,
                    ir.Constant(self.char_pointer_type, None),
                ),
            ),
        )
        color_ready_block = window_proc.append_basic_block(name="control_color_ready")
        proc_builder.cbranch(has_color_properties, color_ready_block, default_block)

        proc_builder.position_at_end(color_ready_block)
        has_text_color = proc_builder.icmp_unsigned(
            "!=",
            text_color,
            ir.Constant(self.char_pointer_type, None),
        )
        set_text_color_block = window_proc.append_basic_block(name="set_control_text_color")
        set_background_block = window_proc.append_basic_block(name="set_control_background")
        proc_builder.cbranch(has_text_color, set_text_color_block, set_background_block)

        proc_builder.position_at_end(set_text_color_block)
        proc_builder.call(
            self.set_text_color_function,
            [
                device_context,
                proc_builder.sub(
                    proc_builder.ptrtoint(text_color, self.int32_type),
                    ir.Constant(self.int32_type, 1),
                ),
            ],
        )
        proc_builder.branch(set_background_block)

        proc_builder.position_at_end(set_background_block)
        is_transparent_background = proc_builder.icmp_unsigned(
            "!=",
            background_transparent,
            ir.Constant(self.char_pointer_type, None),
        )
        transparent_background_block = window_proc.append_basic_block(name="transparent_control_background")
        transparent_icon_background_block = window_proc.append_basic_block(
            name="transparent_icon_background"
        )
        opaque_background_block = window_proc.append_basic_block(name="opaque_control_background")
        proc_builder.cbranch(
            is_transparent_background,
            transparent_background_block,
            opaque_background_block,
        )

        proc_builder.position_at_end(transparent_background_block)
        transparent_icon = proc_builder.icmp_unsigned(
            "!=",
            is_icon_control,
            ir.Constant(self.char_pointer_type, None),
        )
        transparent_icon_block = window_proc.append_basic_block(
            name="transparent_icon_mask_background"
        )
        proc_builder.cbranch(
            transparent_icon,
            transparent_icon_background_block,
            transparent_icon_block,
        )

        proc_builder.position_at_end(transparent_icon_block)
        proc_builder.call(
            self.set_background_mode_function,
            [device_context, ir.Constant(self.int32_type, 1)],
        )
        null_brush = proc_builder.call(
            self.get_stock_object_function,
            [ir.Constant(self.int32_type, 5)],
        )
        proc_builder.ret(proc_builder.ptrtoint(null_brush, self.int64_type))

        proc_builder.position_at_end(transparent_icon_background_block)
        icon_transparent_color = proc_builder.call(
            self.get_pixel_function,
            [
                device_context,
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
            ],
        )
        proc_builder.call(
            self.set_background_color_function,
            [device_context, icon_transparent_color],
        )
        proc_builder.call(
            self.set_background_mode_function,
            [device_context, ir.Constant(self.int32_type, 2)],
        )
        icon_transparent_brush = proc_builder.call(
            self.create_solid_brush_function,
            [icon_transparent_color],
        )
        proc_builder.ret(
            proc_builder.ptrtoint(icon_transparent_brush, self.int64_type)
        )

        proc_builder.position_at_end(opaque_background_block)
        has_background_brush = proc_builder.icmp_unsigned(
            "!=",
            background_brush,
            ir.Constant(self.char_pointer_type, None),
        )
        set_colored_background_block = window_proc.append_basic_block(
            name="set_colored_control_background"
        )
        default_background_block = window_proc.append_basic_block(name="default_control_background")
        proc_builder.cbranch(
            has_background_brush,
            set_colored_background_block,
            default_background_block,
        )
        proc_builder.position_at_end(set_colored_background_block)
        has_background_opacity = proc_builder.icmp_unsigned(
            "!=",
            background_opacity,
            ir.Constant(self.char_pointer_type, None),
        )
        alpha_background_block = window_proc.append_basic_block(
            name="alpha_control_background"
        )
        set_opaque_background_block = window_proc.append_basic_block(
            name="set_opaque_control_background"
        )
        proc_builder.cbranch(
            has_background_opacity,
            alpha_background_block,
            set_opaque_background_block,
        )

        proc_builder.position_at_end(alpha_background_block)
        client_rect_type = ir.LiteralStructType([self.int32_type] * 4)
        client_rect = proc_builder.alloca(client_rect_type, name="interface_client_rect")
        proc_builder.call(
            self.get_client_rect_function,
            [
                control_window,
                proc_builder.bitcast(client_rect, self.char_pointer_type),
            ],
        )
        left = proc_builder.load(
            proc_builder.gep(
                client_rect,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 0)],
            )
        )
        top = proc_builder.load(
            proc_builder.gep(
                client_rect,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 1)],
            )
        )
        right = proc_builder.load(
            proc_builder.gep(
                client_rect,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 2)],
            )
        )
        bottom = proc_builder.load(
            proc_builder.gep(
                client_rect,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 3)],
            )
        )
        memory_dc = proc_builder.call(
            self.create_compatible_dc_function,
            [device_context],
            name="interface_alpha_memory_dc",
        )
        memory_dc_created = proc_builder.icmp_unsigned(
            "!=",
            memory_dc,
            ir.Constant(self.char_pointer_type, None),
        )
        create_alpha_bitmap_block = window_proc.append_basic_block(
            name="create_interface_alpha_bitmap"
        )
        alpha_fallback_block = window_proc.append_basic_block(
            name="interface_alpha_fallback"
        )
        proc_builder.cbranch(
            memory_dc_created,
            create_alpha_bitmap_block,
            alpha_fallback_block,
        )

        proc_builder.position_at_end(create_alpha_bitmap_block)
        memory_bitmap = proc_builder.call(
            self.create_compatible_bitmap_function,
            [
                device_context,
                ir.Constant(self.int32_type, 1),
                ir.Constant(self.int32_type, 1),
            ],
            name="interface_alpha_bitmap",
        )
        memory_bitmap_created = proc_builder.icmp_unsigned(
            "!=",
            memory_bitmap,
            ir.Constant(self.char_pointer_type, None),
        )
        blend_alpha_block = window_proc.append_basic_block(
            name="blend_interface_alpha_background"
        )
        delete_failed_dc_block = window_proc.append_basic_block(
            name="delete_interface_alpha_dc"
        )
        proc_builder.cbranch(
            memory_bitmap_created,
            blend_alpha_block,
            delete_failed_dc_block,
        )

        proc_builder.position_at_end(blend_alpha_block)
        previous_bitmap = proc_builder.call(
            self.select_object_function,
            [memory_dc, memory_bitmap],
        )
        proc_builder.call(
            self.set_pixel_function,
            [
                memory_dc,
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                proc_builder.sub(
                    proc_builder.ptrtoint(background_color, self.int32_type),
                    ir.Constant(self.int32_type, 1),
                ),
            ],
        )
        alpha_value = proc_builder.sub(
            proc_builder.ptrtoint(background_opacity, self.int32_type),
            ir.Constant(self.int32_type, 1),
        )
        alpha_blend_result = proc_builder.call(
            self.alpha_blend_function,
            [
                device_context,
                left,
                top,
                proc_builder.sub(right, left),
                proc_builder.sub(bottom, top),
                memory_dc,
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 1),
                ir.Constant(self.int32_type, 1),
                proc_builder.shl(alpha_value, ir.Constant(self.int32_type, 16)),
            ],
        )
        proc_builder.call(
            self.select_object_function,
            [memory_dc, previous_bitmap],
        )
        proc_builder.call(self.delete_object_function, [memory_bitmap])
        proc_builder.call(self.delete_dc_function, [memory_dc])
        blend_succeeded = proc_builder.icmp_signed(
            "!=",
            alpha_blend_result,
            ir.Constant(self.int32_type, 0),
        )
        alpha_painted_block = window_proc.append_basic_block(
            name="interface_alpha_painted"
        )
        alpha_icon_painted_block = window_proc.append_basic_block(
            name="interface_alpha_icon_painted"
        )
        proc_builder.cbranch(
            blend_succeeded,
            alpha_painted_block,
            alpha_fallback_block,
        )

        proc_builder.position_at_end(alpha_painted_block)
        alpha_icon = proc_builder.icmp_unsigned(
            "!=",
            is_icon_control,
            ir.Constant(self.char_pointer_type, None),
        )
        alpha_icon_block = window_proc.append_basic_block(
            name="alpha_icon_mask_background"
        )
        proc_builder.cbranch(alpha_icon, alpha_icon_painted_block, alpha_icon_block)

        proc_builder.position_at_end(alpha_icon_block)
        proc_builder.call(
            self.set_background_mode_function,
            [device_context, ir.Constant(self.int32_type, 1)],
        )
        alpha_null_brush = proc_builder.call(
            self.get_stock_object_function,
            [ir.Constant(self.int32_type, 5)],
        )
        proc_builder.ret(proc_builder.ptrtoint(alpha_null_brush, self.int64_type))

        proc_builder.position_at_end(alpha_icon_painted_block)
        icon_alpha_brush = proc_builder.call(
            icon_background_brush_function,
            [control_window, device_context, left, top],
        )
        icon_alpha_color = proc_builder.call(
            self.get_pixel_function,
            [device_context, left, top],
        )
        proc_builder.call(
            self.set_background_color_function,
            [device_context, icon_alpha_color],
        )
        proc_builder.call(
            self.set_background_mode_function,
            [device_context, ir.Constant(self.int32_type, 2)],
        )
        proc_builder.ret(proc_builder.ptrtoint(icon_alpha_brush, self.int64_type))

        proc_builder.position_at_end(delete_failed_dc_block)
        proc_builder.call(self.delete_dc_function, [memory_dc])
        proc_builder.branch(alpha_fallback_block)

        proc_builder.position_at_end(alpha_fallback_block)
        proc_builder.call(
            self.set_background_mode_function,
            [device_context, ir.Constant(self.int32_type, 2)],
        )
        proc_builder.ret(proc_builder.ptrtoint(background_brush, self.int64_type))

        proc_builder.position_at_end(set_opaque_background_block)
        proc_builder.call(
            self.set_background_color_function,
            [
                device_context,
                proc_builder.sub(
                    proc_builder.ptrtoint(background_color, self.int32_type),
                    ir.Constant(self.int32_type, 1),
                ),
            ],
        )
        proc_builder.call(
            self.set_background_mode_function,
            [device_context, ir.Constant(self.int32_type, 2)],
        )
        proc_builder.ret(proc_builder.ptrtoint(background_brush, self.int64_type))
        proc_builder.position_at_end(default_background_block)
        proc_builder.call(
            self.set_background_mode_function,
            [device_context, ir.Constant(self.int32_type, 1)],
        )
        default_brush = proc_builder.call(
            self.get_stock_object_function,
            [ir.Constant(self.int32_type, 5)],
        )
        proc_builder.ret(proc_builder.ptrtoint(default_brush, self.int64_type))

        proc_builder.position_at_end(command_check_block)
        is_command = proc_builder.icmp_signed(
            "==",
            window_proc.args[1],
            ir.Constant(self.int32_type, 0x0111),
        )
        proc_builder.cbranch(is_command, command_click_block, default_block)

        proc_builder.position_at_end(command_click_block)
        has_control_source = proc_builder.icmp_unsigned(
            "!=",
            window_proc.args[3],
            ir.Constant(self.int64_type, 0),
        )
        notification_code = proc_builder.lshr(window_proc.args[2], ir.Constant(self.int64_type, 16))
        is_button_click = proc_builder.icmp_unsigned(
            "==",
            proc_builder.and_(notification_code, ir.Constant(self.int64_type, 0xffff)),
            ir.Constant(self.int64_type, 0),
        )
        is_control_click = proc_builder.and_(has_control_source, is_button_click)
        click_record_block = window_proc.append_basic_block(name="record_interface_click")
        proc_builder.cbranch(is_control_click, click_record_block, default_block)

        proc_builder.position_at_end(click_record_block)
        control_id = proc_builder.trunc(
            proc_builder.and_(window_proc.args[2], ir.Constant(self.int64_type, 0xffff)),
            self.int32_type,
        )
        click_flag_pointer = proc_builder.gep(
            self.interface_clicked_global,
            [
                ir.Constant(self.int32_type, 0),
                control_id,
            ],
        )
        proc_builder.atomic_rmw(
            "xchg",
            click_flag_pointer,
            ir.Constant(self.int32_type, 1),
            "release",
        )
        proc_builder.ret(ir.Constant(self.int64_type, 0))

        proc_builder.position_at_end(default_block)
        default_result = proc_builder.call(
            self.default_window_proc_function,
            list(window_proc.args),
        )
        proc_builder.ret(default_result)

        self.emit_interface_creation_function(interface_creation_function)

        window_target = ir.GlobalVariable(
            self.module,
            pointer_type,
            name="vamp_window_target",
        )
        window_target.initializer = ir.Constant(pointer_type, None)
        window_mode = ir.GlobalVariable(
            self.module,
            self.int32_type,
            name="vamp_window_mode",
        )
        window_mode.initializer = ir.Constant(self.int32_type, 0)
        window_count = ir.GlobalVariable(
            self.module,
            self.int32_type,
            name="vamp_window_count",
        )
        window_count.initializer = ir.Constant(self.int32_type, 0)
        self.active_windows_global = ir.GlobalVariable(
            self.module,
            self.int32_type,
            name="vamp_active_windows",
        )
        self.active_windows_global.initializer = ir.Constant(self.int32_type, 0)

        callback_type = ir.FunctionType(
            self.int32_type,
            [pointer_type, self.int64_type],
        )
        callback = ir.Function(
            self.module,
            callback_type,
            name="vamp_enum_windows_callback",
        )
        callback.linkage = "internal"
        callback.args[0].name = "window"
        callback.args[1].name = "context"

        callback_entry = callback.append_basic_block(name="entry")
        title_block = callback.append_basic_block(name="title")
        compare_block = callback.append_basic_block(name="compare")
        list_block = callback.append_basic_block(name="list")
        matched_block = callback.append_basic_block(name="matched")
        close_block = callback.append_basic_block(name="close")
        query_block = callback.append_basic_block(name="query")
        callback_continue = callback.append_basic_block(name="continue")
        callback_stop = callback.append_basic_block(name="stop")
        callback_builder = ir.IRBuilder(callback_entry)
        visible = callback_builder.call(
            self.is_window_visible_function,
            [callback.args[0]],
        )
        is_visible = callback_builder.icmp_signed(
            "!=",
            visible,
            ir.Constant(self.int32_type, 0),
        )
        callback_builder.cbranch(is_visible, title_block, callback_continue)

        callback_builder.position_at_end(title_block)
        title_buffer_type = ir.ArrayType(ir.IntType(8), 512)
        title_buffer = callback_builder.alloca(title_buffer_type, name="window_title")
        title_pointer = callback_builder.bitcast(title_buffer, pointer_type)
        title_length = callback_builder.call(
            self.get_window_text_function,
            [
                callback.args[0],
                title_pointer,
                ir.Constant(self.int32_type, 512),
            ],
        )
        has_title = callback_builder.icmp_signed(
            ">",
            title_length,
            ir.Constant(self.int32_type, 0),
        )
        callback_builder.cbranch(has_title, compare_block, callback_continue)

        callback_builder.position_at_end(compare_block)
        mode = callback_builder.load(window_mode, name="window_operation_mode")
        is_list = callback_builder.icmp_signed(
            "==",
            mode,
            ir.Constant(self.int32_type, 3),
        )
        callback_builder.cbranch(is_list, list_block, matched_block)

        callback_builder.position_at_end(list_block)
        list_format = self.constant_string_pointer("%s\n")
        callback_builder.call(self.printf_function, [list_format, title_pointer])
        listed_count = callback_builder.load(window_count)
        callback_builder.store(
            callback_builder.add(listed_count, ir.Constant(self.int32_type, 1)),
            window_count,
        )
        callback_builder.branch(callback_continue)

        callback_builder.position_at_end(matched_block)
        target = callback_builder.load(window_target)
        comparison = callback_builder.call(
            self.compare_case_insensitive_function,
            [target, title_pointer],
        )
        is_match = callback_builder.icmp_signed(
            "==",
            comparison,
            ir.Constant(self.int32_type, 0),
        )
        callback_builder.cbranch(is_match, close_block, callback_continue)

        callback_builder.position_at_end(close_block)
        mode = callback_builder.load(window_mode)
        is_close = callback_builder.icmp_signed(
            "==",
            mode,
            ir.Constant(self.int32_type, 2),
        )
        callback_builder.cbranch(is_close, query_block, callback_stop)

        callback_builder.position_at_end(query_block)
        close_posted = callback_builder.call(
            self.post_message_function,
            [
                callback.args[0],
                ir.Constant(self.int32_type, 0x0010),
                ir.Constant(self.int64_type, 0),
                ir.Constant(self.int64_type, 0),
            ],
        )
        close_succeeded = callback_builder.icmp_signed(
            "!=",
            close_posted,
            ir.Constant(self.int32_type, 0),
        )
        query_increment = callback.append_basic_block(name="query_increment")
        callback_builder.cbranch(close_succeeded, query_increment, callback_continue)
        callback_builder.position_at_end(query_increment)
        close_count = callback_builder.load(window_count)
        callback_builder.store(
            callback_builder.add(close_count, ir.Constant(self.int32_type, 1)),
            window_count,
        )
        callback_builder.branch(callback_continue)

        callback_builder.position_at_end(callback_continue)
        callback_builder.ret(ir.Constant(self.int32_type, 1))
        callback_builder.position_at_end(callback_stop)
        match_count = callback_builder.load(window_count)
        callback_builder.store(
            callback_builder.add(match_count, ir.Constant(self.int32_type, 1)),
            window_count,
        )
        callback_builder.ret(ir.Constant(self.int32_type, 0))

        operation_type = ir.FunctionType(
            self.int32_type,
            [self.int32_type, pointer_type],
        )
        operation = ir.Function(
            self.module,
            operation_type,
            name="vamp_window_operation",
        )
        operation.linkage = "internal"
        operation.args[0].name = "mode"
        operation.args[1].name = "title"
        op_entry = operation.append_basic_block(name="entry")
        op_finish = operation.append_basic_block(name="finish")
        op_builder = ir.IRBuilder(op_entry)
        op_builder.store(operation.args[0], window_mode)
        op_builder.store(operation.args[1], window_target)
        op_builder.store(ir.Constant(self.int32_type, 0), window_count)
        callback_pointer = op_builder.bitcast(callback, pointer_type)
        op_builder.call(
            self.enum_windows_function,
            [callback_pointer, ir.Constant(self.int64_type, 0)],
            name="enumerated_windows",
        )
        op_builder.branch(op_finish)
        op_builder.position_at_end(op_finish)
        final_count = op_builder.load(window_count, name="window_operation_count")
        op_builder.ret(final_count)

        context_type = ir.LiteralStructType(
            [
                pointer_type,
                pointer_type,
                self.int32_type,
                self.int32_type,
                self.int32_type,
                self.int32_type,
                self.int32_type,
                pointer_type,
            ]
        )
        thread_type = ir.FunctionType(self.int32_type, [pointer_type])
        window_thread = ir.Function(
            self.module,
            thread_type,
            name="vamp_window_thread",
        )
        window_thread.linkage = "internal"
        window_thread.args[0].name = "context"

        thread_entry = window_thread.append_basic_block(name="entry")
        load_icon_block = window_thread.append_basic_block(name="load_icon")
        icon_ready_block = window_thread.append_basic_block(name="icon_ready")
        register_block = window_thread.append_basic_block(name="register")
        class_exists_block = window_thread.append_basic_block(name="class_exists")
        create_block = window_thread.append_basic_block(name="create")
        pump_block = window_thread.append_basic_block(name="message_pump")
        message_dispatch_block = window_thread.append_basic_block(name="message_dispatch")
        message_loop_exit_block = window_thread.append_basic_block(name="message_loop_exit")
        signal_failure_block = window_thread.append_basic_block(name="signal_failure")
        creation_failure_cleanup_block = window_thread.append_basic_block(name="creation_failure_cleanup")
        destroy_unattached_icon_block = window_thread.append_basic_block(name="destroy_unattached_icon")
        creation_failure_ready_block = window_thread.append_basic_block(name="creation_failure_ready")
        thread_exit_block = window_thread.append_basic_block(name="exit")
        decrement_window_block = window_thread.append_basic_block(name="decrement_window_count")
        thread_return_block = window_thread.append_basic_block(name="thread_return")
        thread_builder = ir.IRBuilder(thread_entry)
        context_pointer = thread_builder.bitcast(
            window_thread.args[0],
            context_type.as_pointer(),
        )
        title_pointer = thread_builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 0)],
        )
        event_pointer = thread_builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 1)],
        )
        result_pointer = thread_builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 2)],
        )
        width_pointer = thread_builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 3)],
        )
        height_pointer = thread_builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 4)],
        )
        window_type_pointer = thread_builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 5)],
        )
        resizable_pointer = thread_builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 6)],
        )
        icon_path_pointer = thread_builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 7)],
        )
        title = thread_builder.load(title_pointer, name="window_title")
        event = thread_builder.load(event_pointer, name="window_ready_event")
        configured_width = thread_builder.load(width_pointer, name="configured_window_width")
        configured_height = thread_builder.load(height_pointer, name="configured_window_height")
        configured_type = thread_builder.load(window_type_pointer, name="configured_window_type")
        configured_resizable = thread_builder.load(resizable_pointer, name="configured_window_resizable")
        icon_path = thread_builder.load(icon_path_pointer, name="configured_window_icon_path")
        icon_path_present = thread_builder.icmp_unsigned(
            "!=",
            icon_path,
            ir.Constant(pointer_type, None),
        )
        thread_builder.cbranch(icon_path_present, load_icon_block, icon_ready_block)

        thread_builder.position_at_end(load_icon_block)
        loaded_icon = thread_builder.call(
            self.get_window_icon_function(),
            [icon_path],
            name="loaded_window_icon",
        )
        icon_load_succeeded = thread_builder.icmp_unsigned(
            "!=",
            loaded_icon,
            ir.Constant(pointer_type, None),
        )
        thread_builder.cbranch(icon_load_succeeded, icon_ready_block, signal_failure_block)

        thread_builder.position_at_end(icon_ready_block)
        icon_handle = thread_builder.phi(pointer_type, name="window_icon_handle")
        icon_handle.add_incoming(ir.Constant(pointer_type, None), thread_entry)
        icon_handle.add_incoming(loaded_icon, load_icon_block)
        cls_name = self.constant_string_pointer("VampNativeWindow")
        wnd_class_type = ir.LiteralStructType(
            [
                self.int32_type,
                self.int32_type,
                pointer_type,
                self.int32_type,
                self.int32_type,
                pointer_type,
                pointer_type,
                pointer_type,
                pointer_type,
                pointer_type,
                pointer_type,
                pointer_type,
            ]
        )
        wnd_class = thread_builder.alloca(wnd_class_type, name="window_class")
        class_fields = [
            ir.Constant(self.int32_type, 80),
            ir.Constant(self.int32_type, 0),
            thread_builder.bitcast(window_proc, pointer_type),
            ir.Constant(self.int32_type, 0),
            ir.Constant(self.int32_type, 0),
            thread_builder.call(
                self.get_module_handle_function,
                [ir.Constant(pointer_type, None)],
            ),
        ]
        class_fields.extend([
            ir.Constant(pointer_type, None),
            ir.Constant(pointer_type, None),
            ir.Constant(self.int64_type, 6).inttoptr(pointer_type),
            ir.Constant(pointer_type, None),
        ])
        class_fields.extend([cls_name, ir.Constant(pointer_type, None)])
        for idx, value in enumerate(class_fields):
            field_pointer = thread_builder.gep(
                wnd_class,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)],
            )
            thread_builder.store(value, field_pointer)

        register_result = thread_builder.call(
            self.register_window_class_function,
            [thread_builder.bitcast(wnd_class, pointer_type)],
        )
        registration_failed = thread_builder.icmp_unsigned(
            "==",
            register_result,
            ir.Constant(self.int16_type, 0),
        )
        thread_builder.cbranch(registration_failed, register_block, create_block)

        thread_builder.position_at_end(register_block)
        last_error = thread_builder.call(self.get_last_error_function, [])
        class_already_exists = thread_builder.icmp_unsigned(
            "==",
            last_error,
            ir.Constant(self.int32_type, 1410),
        )
        thread_builder.cbranch(
            class_already_exists,
            class_exists_block,
            creation_failure_cleanup_block,
        )

        thread_builder.position_at_end(class_exists_block)
        thread_builder.branch(create_block)

        thread_builder.position_at_end(create_block)
        fullscreen_type = thread_builder.icmp_signed(
            "==",
            configured_type,
            ir.Constant(self.int32_type, 1),
        )
        positive_width = thread_builder.icmp_signed(
            ">",
            configured_width,
            ir.Constant(self.int32_type, 0),
        )
        positive_height = thread_builder.icmp_signed(
            ">",
            configured_height,
            ir.Constant(self.int32_type, 0),
        )
        valid_dimensions = thread_builder.and_(positive_width, positive_height)
        valid_window_size = thread_builder.or_(fullscreen_type, valid_dimensions)
        create_window_block = window_thread.append_basic_block(name="create_window")
        thread_builder.cbranch(
            valid_window_size,
            create_window_block,
            creation_failure_cleanup_block,
        )
        thread_builder.position_at_end(create_window_block)
        instance_handle = thread_builder.call(
            self.get_module_handle_function,
            [ir.Constant(pointer_type, None)],
        )
        can_resize = thread_builder.icmp_signed(
            "!=",
            configured_resizable,
            ir.Constant(self.int32_type, 0),
        )
        resizable_style = thread_builder.select(
            can_resize,
            ir.Constant(self.int32_type, 0x00CF0000),
            ir.Constant(self.int32_type, 0x00CA0000),
        )
        is_fullscreen = thread_builder.icmp_signed(
            "==",
            configured_type,
            ir.Constant(self.int32_type, 1),
        )
        is_borderless = thread_builder.icmp_signed(
            "==",
            configured_type,
            ir.Constant(self.int32_type, 3),
        )
        is_popup = thread_builder.or_(is_fullscreen, is_borderless)
        window_style = thread_builder.select(
            is_popup,
            ir.Constant(self.int32_type, 0x80000000),
            resizable_style,
        )
        screen_width = thread_builder.call(
            self.get_system_metrics_function,
            [ir.Constant(self.int32_type, 0)],
        )
        screen_height = thread_builder.call(
            self.get_system_metrics_function,
            [ir.Constant(self.int32_type, 1)],
        )
        window_width = thread_builder.select(
            is_fullscreen,
            screen_width,
            configured_width,
        )
        window_height = thread_builder.select(
            is_fullscreen,
            screen_height,
            configured_height,
        )
        window_x = thread_builder.select(
            is_fullscreen,
            ir.Constant(self.int32_type, 0),
            ir.Constant(self.int32_type, -2147483648),
        )
        window_y = thread_builder.select(
            is_fullscreen,
            ir.Constant(self.int32_type, 0),
            ir.Constant(self.int32_type, -2147483648),
        )
        window = thread_builder.call(
            self.create_window_function,
            [
                ir.Constant(self.int32_type, 0),
                cls_name,
                title,
                window_style,
                window_x,
                window_y,
                window_width,
                window_height,
                ir.Constant(pointer_type, None),
                ir.Constant(pointer_type, None),
                instance_handle,
                ir.Constant(pointer_type, None),
            ],
            name="created_window",
        )
        window_failed = thread_builder.icmp_unsigned(
            "==",
            window,
            ir.Constant(pointer_type, None),
        )
        thread_builder.cbranch(
            window_failed,
            creation_failure_cleanup_block,
            pump_block,
        )

        thread_builder.position_at_end(pump_block)
        thread_builder.call(
            self.send_message_function,
            [
                window,
                ir.Constant(self.int32_type, 0x0080),
                ir.Constant(self.int64_type, 1),
                thread_builder.ptrtoint(icon_handle, self.int64_type),
            ],
        )
        thread_builder.call(
            self.send_message_function,
            [
                window,
                ir.Constant(self.int32_type, 0x0080),
                ir.Constant(self.int64_type, 0),
                thread_builder.ptrtoint(icon_handle, self.int64_type),
            ],
        )
        show_command = thread_builder.select(
            thread_builder.icmp_signed(
                "==",
                configured_type,
                ir.Constant(self.int32_type, 2),
            ),
            ir.Constant(self.int32_type, 3),
            ir.Constant(self.int32_type, 5),
        )
        thread_builder.call(
            self.show_window_function,
            [window, show_command],
        )
        thread_builder.call(self.update_window_function, [window])
        thread_builder.store(ir.Constant(self.int32_type, 1), result_pointer)
        thread_builder.atomic_rmw(
            "add",
            self.active_windows_global,
            ir.Constant(self.int32_type, 1),
            "release",
        )
        thread_builder.call(self.set_event_function, [event])
        message_type = ir.LiteralStructType(
            [
                pointer_type,
                self.int32_type,
                self.int64_type,
                self.int64_type,
                self.int32_type,
                ir.ArrayType(self.int32_type, 2),
            ]
        )
        msg = thread_builder.alloca(message_type, name="window_message")
        message_bytes = thread_builder.bitcast(msg, pointer_type)
        thread_builder.branch(message_dispatch_block)

        thread_builder.position_at_end(message_dispatch_block)
        message_result = thread_builder.call(
            self.get_message_function,
            [
                message_bytes,
                ir.Constant(pointer_type, None),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
            ],
        )
        has_message = thread_builder.icmp_signed(
            ">",
            message_result,
            ir.Constant(self.int32_type, 0),
        )
        dispatch_block = window_thread.append_basic_block(name="dispatch_message")
        thread_builder.cbranch(has_message, dispatch_block, message_loop_exit_block)
        thread_builder.position_at_end(dispatch_block)
        thread_builder.call(self.translate_message_function, [message_bytes])
        thread_builder.call(self.dispatch_message_function, [message_bytes])
        thread_builder.branch(message_dispatch_block)

        thread_builder.position_at_end(message_loop_exit_block)
        has_icon = thread_builder.icmp_unsigned(
            "!=",
            icon_handle,
            ir.Constant(pointer_type, None),
        )
        destroy_icon_block = window_thread.append_basic_block(name="destroy_window_icon")
        finish_message_loop_block = window_thread.append_basic_block(name="finish_message_loop")
        thread_builder.cbranch(has_icon, destroy_icon_block, finish_message_loop_block)
        thread_builder.position_at_end(destroy_icon_block)
        thread_builder.call(self.destroy_icon_function, [icon_handle])
        thread_builder.branch(finish_message_loop_block)
        thread_builder.position_at_end(finish_message_loop_block)
        thread_builder.branch(thread_exit_block)

        thread_builder.position_at_end(signal_failure_block)
        thread_builder.store(ir.Constant(self.int32_type, 0), result_pointer)
        thread_builder.call(self.set_event_function, [event])
        thread_builder.branch(thread_exit_block)

        thread_builder.position_at_end(creation_failure_cleanup_block)
        failed_creation_has_icon = thread_builder.icmp_unsigned(
            "!=",
            icon_handle,
            ir.Constant(pointer_type, None),
        )
        thread_builder.cbranch(
            failed_creation_has_icon,
            destroy_unattached_icon_block,
            creation_failure_ready_block,
        )
        thread_builder.position_at_end(destroy_unattached_icon_block)
        thread_builder.call(self.destroy_icon_function, [icon_handle])
        thread_builder.branch(creation_failure_ready_block)
        thread_builder.position_at_end(creation_failure_ready_block)
        thread_builder.branch(signal_failure_block)

        thread_builder.position_at_end(thread_exit_block)
        was_created = thread_builder.load(result_pointer)
        successful_window = thread_builder.icmp_signed(
            "!=",
            was_created,
            ir.Constant(self.int32_type, 0),
        )
        thread_builder.cbranch(
            successful_window,
            decrement_window_block,
            thread_return_block,
        )
        thread_builder.position_at_end(decrement_window_block)
        thread_builder.atomic_rmw(
            "sub",
            self.active_windows_global,
            ir.Constant(self.int32_type, 1),
            "release",
        )
        thread_builder.branch(thread_return_block)
        thread_builder.position_at_end(thread_return_block)
        thread_builder.ret(ir.Constant(self.int32_type, 0))

        self.window_runtime_functions = {
            "thread": window_thread,
            "context_type": context_type,
            "operation": operation,
        }
        return self.window_runtime_functions

    def get_window_operation_function(self):
        return self.get_window_runtime_functions()["operation"]

    def get_process_operation_function(self):
        if self.process_operation_function is not None:
            return self.process_operation_function

        function_type = ir.FunctionType(
            self.int32_type,
            [self.int32_type, self.char_pointer_type],
        )
        fn = ir.Function(
            self.module,
            function_type,
            name="vamp_os_process_operation",
        )
        fn.linkage = "internal"
        fn.args[0].name = "operation"
        fn.args[1].name = "process_name"
        self.process_operation_function = fn

        previous_builder = self.builder
        previous_variable_pointers = self.variable_pointers
        previous_type_information = self.type_information
        previous_array_information = self.array_information
        previous_dictionary_information = self.dictionary_information
        previous_constant_variables = self.constant_variables
        self.variable_pointers = {}
        self.type_information = {}
        self.array_information = {}
        self.dictionary_information = {}
        self.constant_variables = set()

        entry = fn.append_basic_block(name="entry")
        first_entry = fn.append_basic_block(name="process_first_entry")
        process_entry = fn.append_basic_block(name="process_entry")
        list_entry = fn.append_basic_block(name="process_list_entry")
        compare_entry = fn.append_basic_block(name="process_compare_entry")
        matched_entry = fn.append_basic_block(name="process_matched_entry")
        exists_match = fn.append_basic_block(name="process_exists_match")
        terminate_entry = fn.append_basic_block(name="process_terminate_entry")
        open_failed = fn.append_basic_block(name="process_open_failed")
        terminate_success = fn.append_basic_block(name="process_terminate_success")
        terminate_failed = fn.append_basic_block(name="process_terminate_failed")
        close_process_success = fn.append_basic_block(name="process_close_success")
        next_entry = fn.append_basic_block(name="process_next_entry")
        finish = fn.append_basic_block(name="process_finish")
        snapshot_failed = fn.append_basic_block(name="process_snapshot_failed")

        self.builder = ir.IRBuilder(entry)
        process_info_type = ir.ArrayType(ir.IntType(8), 304)
        process_info = self.builder.alloca(process_info_type, name="process_entry")
        process_info_bytes = self.builder.bitcast(
            process_info,
            self.char_pointer_type,
            name="process_entry_bytes",
        )
        process_info_size_pointer = self.builder.bitcast(
            process_info_bytes,
            self.int32_type.as_pointer(),
            name="process_entry_size_pointer",
        )
        self.builder.store(
            ir.Constant(self.int32_type, 304),
            process_info_size_pointer,
        )
        process_count_pointer = self.builder.alloca(
            self.int32_type,
            name="matching_process_count",
        )
        self.builder.store(ir.Constant(self.int32_type, 0), process_count_pointer)

        snapshot = self.builder.call(
            self.create_process_snapshot_function,
            [ir.Constant(self.int32_type, 0x2), ir.Constant(self.int32_type, 0)],
            name="process_snapshot",
        )
        invalid_snapshot = ir.Constant(self.int64_type, -1).inttoptr(
            self.char_pointer_type
        )
        snapshot_is_invalid = self.builder.icmp_unsigned(
            "==",
            snapshot,
            invalid_snapshot,
            name="process_snapshot_failed",
        )
        self.builder.cbranch(snapshot_is_invalid, snapshot_failed, first_entry)

        self.builder.position_at_end(snapshot_failed)
        error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not enumerate running programs (code %d)\n")
        )[0]
        snapshot_error = self.builder.call(self.get_last_error_function, [])
        self.builder.call(self.printf_function, [error_format, snapshot_error])
        self.builder.ret(ir.Constant(self.int32_type, -1))

        self.builder.position_at_end(first_entry)
        has_first_process = self.builder.call(
            self.process32_first_function,
            [snapshot, process_info_bytes],
            name="has_first_process",
        )
        has_first_process = self.builder.icmp_signed(
            "!=",
            has_first_process,
            ir.Constant(self.int32_type, 0),
        )
        self.builder.cbranch(has_first_process, process_entry, finish)

        self.builder.position_at_end(process_entry)
        operation_is_list = self.builder.icmp_signed(
            "==",
            fn.args[0],
            ir.Constant(self.int32_type, 3),
        )
        self.builder.cbranch(operation_is_list, list_entry, compare_entry)

        self.builder.position_at_end(list_entry)
        executable_name_pointer = self.builder.gep(
            process_info_bytes,
            [ir.Constant(self.int32_type, 44)],
            name="process_executable_name",
        )
        process_line_format = self.visit_LiteralNode(LiteralNode("str", "%s\n"))[0]
        self.builder.call(
            self.printf_function,
            [process_line_format, executable_name_pointer],
        )
        listed_count = self.builder.load(process_count_pointer)
        self.builder.store(
            self.builder.add(listed_count, ir.Constant(self.int32_type, 1)),
            process_count_pointer,
        )
        self.builder.branch(next_entry)

        self.builder.position_at_end(compare_entry)
        executable_name_pointer = self.builder.gep(
            process_info_bytes,
            [ir.Constant(self.int32_type, 44)],
            name="process_executable_name",
        )
        name_matches = self.builder.call(
            self.compare_case_insensitive_function,
            [fn.args[1], executable_name_pointer],
            name="process_name_matches",
        )
        name_matches = self.builder.icmp_signed(
            "==",
            name_matches,
            ir.Constant(self.int32_type, 0),
        )
        self.builder.cbranch(name_matches, matched_entry, next_entry)

        self.builder.position_at_end(matched_entry)
        operation_is_remove = self.builder.icmp_signed(
            "==",
            fn.args[0],
            ir.Constant(self.int32_type, 2),
        )
        self.builder.cbranch(operation_is_remove, terminate_entry, exists_match)

        self.builder.position_at_end(exists_match)
        existing_count = self.builder.load(process_count_pointer)
        self.builder.store(
            self.builder.add(existing_count, ir.Constant(self.int32_type, 1)),
            process_count_pointer,
        )
        self.builder.branch(next_entry)

        self.builder.position_at_end(terminate_entry)
        process_id_pointer = self.builder.gep(
            process_info_bytes,
            [ir.Constant(self.int32_type, 8)],
            name="process_id_pointer",
        )
        process_id = self.builder.load(
            self.builder.bitcast(process_id_pointer, self.int32_type.as_pointer()),
            name="process_id",
        )
        process_handle = self.builder.call(
            self.open_process_function,
            [
                ir.Constant(self.int32_type, 0x0001),
                ir.Constant(self.int32_type, 0),
                process_id,
            ],
            name="process_handle",
        )
        handle_is_null = self.builder.icmp_unsigned(
            "==",
            process_handle,
            ir.Constant(self.char_pointer_type, None),
        )
        self.builder.cbranch(handle_is_null, open_failed, close_process_success)

        self.builder.position_at_end(open_failed)
        open_error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not open program '%s' (code %d)\n")
        )[0]
        open_error = self.builder.call(self.get_last_error_function, [])
        self.builder.call(
            self.printf_function,
            [open_error_format, fn.args[1], open_error],
        )
        self.builder.branch(next_entry)

        self.builder.position_at_end(close_process_success)
        was_terminated = self.builder.call(
            self.terminate_process_function,
            [process_handle, ir.Constant(self.int32_type, 1)],
            name="program_was_terminated",
        )
        was_terminated = self.builder.icmp_signed(
            "!=",
            was_terminated,
            ir.Constant(self.int32_type, 0),
        )
        self.builder.cbranch(was_terminated, terminate_success, terminate_failed)

        self.builder.position_at_end(terminate_success)
        removed_count = self.builder.load(process_count_pointer)
        self.builder.store(
            self.builder.add(removed_count, ir.Constant(self.int32_type, 1)),
            process_count_pointer,
        )
        self.builder.call(self.close_handle_function, [process_handle])
        self.builder.branch(next_entry)

        self.builder.position_at_end(terminate_failed)
        terminate_error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not terminate program '%s' (code %d)\n")
        )[0]
        terminate_error = self.builder.call(self.get_last_error_function, [])
        self.builder.call(
            self.printf_function,
            [terminate_error_format, fn.args[1], terminate_error],
        )
        self.builder.call(self.close_handle_function, [process_handle])
        self.builder.branch(next_entry)

        self.builder.position_at_end(next_entry)
        has_next_process = self.builder.call(
            self.process32_next_function,
            [snapshot, process_info_bytes],
            name="has_next_process",
        )
        has_next_process = self.builder.icmp_signed(
            "!=",
            has_next_process,
            ir.Constant(self.int32_type, 0),
        )
        self.builder.cbranch(has_next_process, process_entry, finish)

        self.builder.position_at_end(finish)
        self.builder.call(self.close_handle_function, [snapshot])
        final_process_count = self.builder.load(
            process_count_pointer,
            name="final_process_count",
        )
        self.builder.ret(final_process_count)

        self.builder = previous_builder
        self.variable_pointers = previous_variable_pointers
        self.type_information = previous_type_information
        self.array_information = previous_array_information
        self.dictionary_information = previous_dictionary_information
        self.constant_variables = previous_constant_variables
        return fn

    def visit_LibraryCallNode(self, node):
        if node.library_name == "os" and "os" not in self.imported_libraries:
            raise NameError("Library 'os' is not imported. Add 'import os' at top of file.")

        if node.library_name == "os":
            if node.method_name == "Sleep":
                self.require_argument_count(node, 1)
                milliseconds, milliseconds_type = self.visit(node.arguments[0])
                if milliseconds_type != "int":
                    raise TypeError("os.Sleep expects an integer number of milliseconds")
                valid_block = self.builder.function.append_basic_block(name="sleep_valid")
                invalid_block = self.builder.function.append_basic_block(name="sleep_invalid")
                merge_block = self.builder.function.append_basic_block(name="sleep_end")
                is_nonnegative = self.builder.icmp_signed(
                    ">=",
                    milliseconds,
                    ir.Constant(self.int32_type, 0),
                )
                self.builder.cbranch(is_nonnegative, valid_block, invalid_block)

                self.builder.position_at_end(invalid_block)
                error_message = self.visit_LiteralNode(
                    LiteralNode("str", "Error: os.Sleep duration cannot be negative\n")
                )[0]
                self.builder.call(self.printf_function, [error_message])
                self.builder.branch(merge_block)

                self.builder.position_at_end(valid_block)
                self.emit_interface_message_pump()
                self.builder.call(self.sleep_function, [milliseconds])
                self.builder.branch(merge_block)
                self.builder.position_at_end(merge_block)
                return None, "void"
            if node.method_name == "Make_Directory":
                path_value = self.get_directory_path_argument(node)
                absolute_path, _ = self.emit_absolute_path(path_value)
                null_pointer = ir.Constant(self.char_pointer_type, None)
                res = self.builder.call(
                    self.create_directory_function,
                    [null_pointer, absolute_path, null_pointer],
                )
                self.builder.call(self.free_function, [absolute_path])
                return res, "int"
            if node.method_name == "Get_Directory":
                path_value = self.get_directory_path_argument(node)
                return self.emit_absolute_directory_path(path_value)
            if node.method_name == "List_Directory":
                path_value = self.get_directory_path_argument(node)
                absolute_path, _ = self.emit_absolute_path(path_value)
                res = self.emit_directory_listing(absolute_path)
                self.builder.call(self.free_function, [absolute_path])
                return res
            if node.method_name == "Remove_Directory":
                path_value = self.get_directory_path_argument(node)
                absolute_path, _ = self.emit_absolute_path(path_value)
                res = self.emit_directory_removal(absolute_path)
                self.builder.call(self.free_function, [absolute_path])
                return res
            if node.method_name == "Directory_Exists":
                path_value = self.get_directory_path_argument(node)
                res = self.builder.call(self.get_file_attributes_function, [path_value])
                is_valid_path = self.builder.icmp_signed(
                    "!=",
                    res,
                    ir.Constant(self.int32_type, -1),
                )
                is_directory = self.builder.icmp_unsigned(
                    "!=",
                    self.builder.and_(res, ir.Constant(self.int32_type, 0x10)),
                    ir.Constant(self.int32_type, 0),
                )
                exists = self.builder.and_(is_valid_path, is_directory)
                return exists, "bool"
            if node.method_name == "Make_Window":
                if len(node.arguments) not in (1, 2):
                    raise TypeError(
                        "os.Make_Window expects a title and an optional window configuration"
                    )
                title, title_type = self.visit(node.arguments[0])
                if title_type != "str":
                    raise TypeError("os.Make_Window title must be a string")

                width = ir.Constant(self.int32_type, 800)
                height = ir.Constant(self.int32_type, 600)
                resizable = ir.Constant(self.int32_type, 1)
                window_type = 0
                icon_path = ir.Constant(self.char_pointer_type, None)
                if len(node.arguments) == 2:
                    cfg = node.arguments[1]
                    if not isinstance(cfg, WindowConfigNode):
                        raise TypeError(
                            "os.Make_Window configuration must use a window property block"
                        )
                    supported_properties = {"icon", "size", "resizable", "type"}
                    unknown_properties = set(cfg.properties) - supported_properties
                    if unknown_properties:
                        unknown = sorted(unknown_properties)[0]
                        raise SyntaxError(f"Unknown window property '{unknown}'")

                    icon_expression = cfg.properties.get("icon")
                    if icon_expression is not None:
                        icon_path, icon_type = self.visit(icon_expression)
                        if icon_type != "str":
                            raise TypeError("Window property 'icon' must be a string image path")

                    size_expression = cfg.properties.get("size")
                    if size_expression is not None:
                        if not isinstance(size_expression, WindowSizeNode):
                            raise TypeError("Window property 'size' must be a pair of integers")
                        width, width_type = self.visit(size_expression.width)
                        height, height_type = self.visit(size_expression.height)
                        if width_type != "int" or height_type != "int":
                            raise TypeError("Window property 'size' values must be integers")

                    resizable_expression = cfg.properties.get("resizable")
                    if resizable_expression is not None:
                        resizable, resizable_type = self.visit(resizable_expression)
                        if resizable_type != "bool":
                            raise TypeError("Window property 'resizable' must be a bool")
                        resizable = self.builder.zext(
                            resizable,
                            self.int32_type,
                            name="window_resizable",
                        )

                    type_expression = cfg.properties.get("type")
                    if type_expression is not None:
                        if not isinstance(type_expression, LiteralNode) or type_expression.literal_type != "str":
                            raise TypeError("Window property 'type' must be a string literal")
                        window_types = {
                            "Windowed": 0,
                            "Full Screen": 1,
                            "Maximized": 2,
                            "Borderless": 3,
                        }
                        if type_expression.value not in window_types:
                            raise ValueError(
                                "Window property 'type' must be 'Windowed', 'Full Screen', "
                                "'Maximized', or 'Borderless'"
                            )
                        window_type = window_types[type_expression.value]

                runtime = self.get_window_runtime_functions()
                fn = self.builder.function
                create_event_block = fn.append_basic_block(name="window_create_event")
                create_thread_block = fn.append_basic_block(name="window_create_thread")
                wait_block = fn.append_basic_block(name="window_wait_ready")
                success_block = fn.append_basic_block(name="window_create_success")
                error_block = fn.append_basic_block(name="window_create_error")
                merge_block = fn.append_basic_block(name="window_create_end")
                event = self.builder.call(
                    self.create_event_function,
                    [
                        ir.Constant(self.char_pointer_type, None),
                        ir.Constant(self.int32_type, 1),
                        ir.Constant(self.int32_type, 0),
                        ir.Constant(self.char_pointer_type, None),
                    ],
                    name="window_ready_event",
                )
                event_failed = self.builder.icmp_unsigned(
                    "==",
                    event,
                    ir.Constant(self.char_pointer_type, None),
                )
                self.builder.cbranch(event_failed, error_block, create_event_block)

                self.builder.position_at_end(create_event_block)
                ctx = self.allocate_bytes(
                    ir.Constant(
                        self.int64_type,
                        self.module.data_layout.get_abi_size(runtime["context_type"])
                        if self.module.data_layout
                        else 48,
                    ),
                    name="window_thread_context",
                )
                context_pointer = self.builder.bitcast(
                    ctx,
                    runtime["context_type"].as_pointer(),
                )
                title_slot = self.builder.gep(
                    context_pointer,
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 0)],
                )
                event_slot = self.builder.gep(
                    context_pointer,
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 1)],
                )
                result_slot = self.builder.gep(
                    context_pointer,
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 2)],
                )
                self.builder.store(title, title_slot)
                self.builder.store(event, event_slot)
                self.builder.store(ir.Constant(self.int32_type, 0), result_slot)
                for field_index, value in (
                    (3, width),
                    (4, height),
                    (5, ir.Constant(self.int32_type, window_type)),
                    (6, resizable),
                    (7, icon_path),
                ):
                    field_pointer = self.builder.gep(
                        context_pointer,
                        [
                            ir.Constant(self.int32_type, 0),
                            ir.Constant(self.int32_type, field_index),
                        ],
                    )
                    self.builder.store(value, field_pointer)
                self.builder.branch(create_thread_block)

                self.builder.position_at_end(create_thread_block)
                thread = self.builder.call(
                    self.create_thread_function,
                    [
                        ir.Constant(self.char_pointer_type, None),
                        ir.Constant(self.int64_type, 0),
                        self.builder.bitcast(runtime["thread"], self.char_pointer_type),
                        ctx,
                        ir.Constant(self.int32_type, 0),
                        ir.Constant(self.char_pointer_type, None),
                    ],
                    name="window_thread",
                )
                thread_failed = self.builder.icmp_unsigned(
                    "==",
                    thread,
                    ir.Constant(self.char_pointer_type, None),
                )
                thread_failed_block = fn.append_basic_block(name="window_thread_failed")
                self.builder.cbranch(thread_failed, thread_failed_block, wait_block)

                self.builder.position_at_end(thread_failed_block)
                self.builder.call(self.close_handle_function, [event])
                self.builder.call(self.free_function, [ctx])
                self.builder.branch(error_block)

                self.builder.position_at_end(wait_block)
                self.builder.call(
                    self.wait_for_single_object_function,
                    [event, ir.Constant(self.int32_type, -1)],
                )
                self.builder.call(self.close_handle_function, [event])
                self.builder.call(self.close_handle_function, [thread])
                window_was_created = self.builder.load(result_slot)
                self.builder.call(self.free_function, [ctx])
                self.builder.cbranch(
                    self.builder.icmp_signed(
                        "!=",
                        window_was_created,
                        ir.Constant(self.int32_type, 0),
                    ),
                    success_block,
                    error_block,
                )

                self.builder.position_at_end(success_block)
                self.builder.branch(merge_block)
                success_predecessor = self.builder.block

                self.builder.position_at_end(error_block)
                error_format = self.visit_LiteralNode(
                    LiteralNode(
                        "str",
                        "Error: could not create window '%s' (check the image path and size; Windows error %d)\n",
                    )
                )[0]
                error_code = self.builder.call(self.get_last_error_function, [])
                self.builder.call(
                    self.printf_function,
                    [error_format, title, error_code],
                )
                self.builder.branch(merge_block)
                error_predecessor = self.builder.block

                self.builder.position_at_end(merge_block)
                succeeded = self.builder.phi(self.bool_type, name="window_create_result")
                succeeded.add_incoming(ir.Constant(self.bool_type, 0), error_predecessor)
                succeeded.add_incoming(ir.Constant(self.bool_type, 1), success_predecessor)
                return succeeded, "bool"
            if node.method_name == "Make_Interface":
                self.require_argument_count(node, 4)
                type_expression, window_title_expression, name_expression, cfg = node.arguments
                if not isinstance(type_expression, LiteralNode) or type_expression.literal_type != "str":
                    raise TypeError("os.Make_Interface type must be a string literal")
                interface_type = type_expression.value.lower()
                if interface_type not in ("label", "button", "frame", "icon"):
                    raise ValueError(
                        "os.Make_Interface type must be 'label', 'button', 'frame', or 'icon'"
                    )
                key = self.get_interface_key(window_title_expression, name_expression)
                if not isinstance(cfg, WindowConfigNode):
                    raise TypeError("os.Make_Interface requires a parenthesized property block")

                common_properties = {"size", "position", "visible"}
                common_properties.add("layer")
                type_properties = {
                    "label": {
                        "text", "text_color", "font", "text_size", "text_transparency",
                        "background_color", "background_transparency", "editable",
                    },
                    "button": {
                        "text", "icon", "text_color", "font", "text_size",
                        "text_transparency", "background_color", "background_transparency",
                    },
                    "frame": {"background_color", "background_transparency"},
                    "icon": {"icon", "background_color", "background_transparency"},
                }
                supported_properties = common_properties | type_properties[interface_type]
                unknown_properties = set(cfg.properties) - supported_properties
                if unknown_properties:
                    unknown = sorted(unknown_properties)[0]
                    raise SyntaxError(
                        f"Property '{unknown}' is not supported for interface type '{interface_type}'"
                    )
                for required_property in ("size", "position"):
                    if required_property not in cfg.properties:
                        raise SyntaxError(
                            f"os.Make_Interface requires the '{required_property}' property"
                        )

                editable_expression = cfg.properties.get("editable")
                editable = False
                if editable_expression is not None:
                    if not isinstance(editable_expression, LiteralNode) or editable_expression.literal_type != "bool":
                        raise TypeError("Interface property 'editable' must be true or false")
                    editable = editable_expression.value
                if interface_type != "label" and editable_expression is not None:
                    raise SyntaxError("Interface property 'editable' is only valid for labels")

                text_expression = cfg.properties.get("text")
                icon_expression = cfg.properties.get("icon")
                if text_expression is not None and interface_type in ("label", "button"):
                    text_value, text_type = self.visit(text_expression)
                    if text_type != "str":
                        raise TypeError("Interface property 'text' must be a string")
                else:
                    text_value = self.visit_LiteralNode(LiteralNode("str", ""))[0]

                if interface_type == "button" and text_expression is not None and icon_expression is not None:
                    raise SyntaxError("A button can use 'text' or 'icon', not both")
                if interface_type == "button" and text_expression is None and icon_expression is None:
                    raise SyntaxError("A button requires either 'text' or 'icon'")
                if interface_type == "button" and icon_expression is not None and {
                    "text_color",
                    "font",
                    "text_size",
                    "text_transparency",
                } & set(cfg.properties):
                    raise SyntaxError(
                        "Text properties cannot be used on an icon-only button"
                    )
                if interface_type == "icon" and icon_expression is None:
                    raise SyntaxError("Interface type 'icon' requires the 'icon' property")
                if icon_expression is not None and interface_type not in ("button", "icon"):
                    raise SyntaxError("Interface property 'icon' is only valid for buttons and icons")
                if icon_expression is not None:
                    icon_path, icon_type = self.visit(icon_expression)
                    if icon_type != "str":
                        raise TypeError("Interface property 'icon' must be a string path")

                size_expression = cfg.properties["size"]
                position_expression = cfg.properties["position"]
                if not isinstance(size_expression, WindowSizeNode):
                    raise TypeError("Interface property 'size' must be a pair of integers")
                if not isinstance(position_expression, WindowPointNode):
                    raise TypeError("Interface property 'position' must be a pair of integers")
                width, width_type = self.visit(size_expression.width)
                height, height_type = self.visit(size_expression.height)
                x_position, x_type = self.visit(position_expression.x)
                y_position, y_type = self.visit(position_expression.y)
                if (width_type, height_type, x_type, y_type) != ("int", "int", "int", "int"):
                    raise TypeError("Interface size and position values must be integers")

                visible_expression = cfg.properties.get(
                    "visible",
                    LiteralNode("bool", True),
                )
                visible_value, visible_type = self.visit(visible_expression)
                if visible_type != "bool":
                    raise TypeError("Interface property 'visible' must be a bool")
                layer_expression = cfg.properties.get(
                    "layer",
                    LiteralNode("int", 0),
                )
                layer_value, layer_type = self.visit(layer_expression)
                if layer_type != "int":
                    raise TypeError("Interface property 'layer' must be an int")

                text_color_expression = cfg.properties.get("text_color")
                text_transparency_expression = cfg.properties.get("text_transparency")
                background_color_expression = cfg.properties.get("background_color")
                background_transparency_expression = cfg.properties.get("background_transparency")
                text_color = None
                background_color = None
                system_face = 0x00ffffff

                if text_color_expression is not None or text_transparency_expression is not None:
                    raw_text_color = (
                        self.parse_interface_color(text_color_expression, "text_color")
                        if text_color_expression is not None
                        else 0
                    )
                    text_opacity = 1.0
                    if text_transparency_expression is not None:
                        if not isinstance(text_transparency_expression, LiteralNode) or text_transparency_expression.literal_type not in ("float", "int"):
                            raise TypeError("Interface property 'text_transparency' must be a number from 0.0 to 1.0")
                        text_opacity = float(text_transparency_expression.value)
                        if not 0.0 <= text_opacity <= 1.0:
                            raise ValueError("Interface property 'text_transparency' must be from 0.0 to 1.0")
                    text_color = self.blend_color(raw_text_color, system_face, text_opacity)

                background_transparency = 0.0
                if background_transparency_expression is not None:
                    if not isinstance(background_transparency_expression, LiteralNode) or background_transparency_expression.literal_type not in ("float", "int"):
                        raise TypeError("Interface property 'background_transparency' must be a number from 0.0 to 1.0")
                    background_transparency = float(background_transparency_expression.value)
                    if not 0.0 <= background_transparency <= 1.0:
                        raise ValueError("Interface property 'background_transparency' must be from 0.0 to 1.0")
                background_opacity = background_transparency
                if background_color_expression is not None:
                    raw_background_color = self.parse_interface_color(
                        background_color_expression,
                        "background_color",
                    )
                    background_color = raw_background_color
                elif background_transparency_expression is not None and background_opacity > 0.0:
                    background_color = system_face

                if text_color_expression is not None or text_transparency_expression is not None:
                    effective_background = (
                        background_color if background_color is not None else system_face
                    )
                    text_color = self.blend_color(
                        raw_text_color,
                        effective_background,
                        text_opacity,
                    )
                font_expression = cfg.properties.get("font")
                text_size_expression = cfg.properties.get("text_size")
                font_name = font_expression.value if isinstance(font_expression, LiteralNode) and font_expression.literal_type == "str" else "Segoe UI"
                if font_expression is not None and (not isinstance(font_expression, LiteralNode) or font_expression.literal_type != "str"):
                    raise TypeError("Interface property 'font' must be a string literal")
                font_size = ir.Constant(self.int32_type, 16)
                if text_size_expression is not None:
                    if not isinstance(text_size_expression, LiteralNode) or text_size_expression.literal_type != "int":
                        raise TypeError("Interface property 'text_size' must be a positive integer literal")
                    if text_size_expression.value <= 0:
                        raise ValueError("Interface property 'text_size' must be positive")
                    font_size = ir.Constant(self.int32_type, text_size_expression.value)

                control_id = self.register_interface(
                    key,
                    interface_type,
                    editable,
                )
                cls_name = {
                    "label": "EDIT" if editable else "STATIC",
                    "button": (
                        "STATIC"
                        if background_color_expression is not None
                        or background_transparency_expression is not None
                        else "BUTTON"
                    ),
                    "frame": "STATIC",
                    "icon": "STATIC",
                }[interface_type]
                control_style = 0x44000000
                if interface_type == "button":
                    control_style |= 0x00010000
                    if icon_expression is not None:
                        control_style |= (
                            0x00000103
                            if background_color_expression is not None
                            or background_transparency_expression is not None
                            else 0x00000040
                        )
                    elif (
                        background_color_expression is not None
                        or background_transparency_expression is not None
                    ):
                        control_style |= 0x00000301
                elif interface_type == "icon":
                    control_style |= 0x00000003
                elif editable:
                    control_style |= 0x00010000 | 0x00000080
                has_background_configuration = (
                    background_color_expression is not None
                    or background_transparency_expression is not None
                )
                if has_background_configuration and background_opacity == 0.0:
                    background_mode = 1
                elif has_background_configuration and background_opacity < 1.0:
                    alpha = max(1, int(background_opacity * 255 + 0.5))
                    background_mode = 3 + alpha
                elif background_color is not None:
                    background_mode = 2
                else:
                    background_mode = 0

                font_enabled = font_expression is not None or text_size_expression is not None
                font_name_value = self.visit_LiteralNode(
                    LiteralNode("str", font_name if font_enabled else "")
                )[0]
                icon_path_value = (
                    icon_path if icon_expression is not None else
                    ir.Constant(self.char_pointer_type, None)
                )
                icon_kind = (
                    1
                    if interface_type == "button"
                    and background_color_expression is None
                    and background_transparency_expression is None
                    else 2
                ) if icon_expression is not None else 0
                ex_style = (
                    0
                    if editable or background_mode == 2 or background_mode > 2
                    else 0x00000020
                )
                interface_request_type = self.get_interface_request_type()
                interface_request = self.builder.alloca(
                    interface_request_type,
                    name="interface_creation_request",
                )
                request_values = [
                    self.visit_LiteralNode(LiteralNode("str", cls_name))[0],
                    text_value,
                    ir.Constant(self.int32_type, control_style),
                    x_position,
                    y_position,
                    width,
                    height,
                    ir.Constant(self.int32_type, control_id),
                    ir.Constant(self.int32_type, ex_style),
                    layer_value,
                    self.builder.zext(visible_value, self.int32_type),
                    ir.Constant(
                        self.int32_type,
                        text_color + 1 if text_color is not None else 0,
                    ),
                    ir.Constant(self.int32_type, background_mode),
                    ir.Constant(self.int32_type, background_color or 0),
                    font_size if font_enabled else ir.Constant(self.int32_type, 0),
                    font_name_value,
                    icon_path_value,
                    ir.Constant(self.int32_type, icon_kind),
                    ir.Constant(self.int32_type, -1),
                ]
                for field_index, field_value in enumerate(request_values):
                    field_pointer = self.builder.gep(
                        interface_request,
                        [
                            ir.Constant(self.int32_type, 0),
                            ir.Constant(self.int32_type, field_index),
                        ],
                    )
                    self.builder.store(field_value, field_pointer)

                null_pointer = ir.Constant(self.char_pointer_type, None)
                window_title = self.visit_LiteralNode(
                    LiteralNode("str", key[0])
                )[0]
                parent_window = self.builder.call(
                    self.get_interface_parent_function(),
                    [window_title],
                    name="interface_parent_window",
                )
                fn = self.builder.function
                missing_parent_block = fn.append_basic_block(
                    name="interface_parent_missing"
                )
                create_control_block = fn.append_basic_block(
                    name="interface_create_control"
                )
                merge_block = fn.append_basic_block(name="interface_create_end")
                parent_found = self.builder.icmp_unsigned("!=", parent_window, null_pointer)
                self.builder.cbranch(
                    parent_found,
                    create_control_block,
                    missing_parent_block,
                )

                self.builder.position_at_end(missing_parent_block)
                missing_parent_format = self.visit_LiteralNode(
                    LiteralNode(
                        "str",
                        "Error: interface parent window '%s' was not found\n",
                    )
                )[0]
                self.builder.call(
                    self.printf_function,
                    [missing_parent_format, window_title],
                )
                self.builder.branch(merge_block)
                missing_parent_predecessor = self.builder.block

                self.builder.position_at_end(create_control_block)
                created_control = self.builder.call(
                    self.send_message_function,
                    [
                        parent_window,
                        ir.Constant(self.int32_type, 0x8001),
                        ir.Constant(self.int64_type, 0),
                        self.builder.ptrtoint(interface_request, self.int64_type),
                    ],
                    name="created_interface_control",
                )
                succeeded = self.builder.icmp_unsigned(
                    "!=",
                    created_control,
                    ir.Constant(self.int64_type, 0),
                    name="interface_created",
                )
                report_failure_block = fn.append_basic_block(
                    name="interface_create_report_failure"
                )
                created_block = fn.append_basic_block(
                    name="interface_created_successfully"
                )
                self.builder.cbranch(succeeded, created_block, report_failure_block)

                self.builder.position_at_end(report_failure_block)
                error_pointer = self.builder.gep(
                    interface_request,
                    [
                        ir.Constant(self.int32_type, 0),
                        ir.Constant(self.int32_type, 18),
                    ],
                )
                error_code = self.builder.load(error_pointer)
                unhandled_request_block = fn.append_basic_block(
                    name="interface_request_unhandled"
                )
                win32_error_block = fn.append_basic_block(
                    name="interface_create_windows_error"
                )
                has_error_code = self.builder.icmp_signed(
                    "!=",
                    error_code,
                    ir.Constant(self.int32_type, -1),
                )
                self.builder.cbranch(
                    has_error_code,
                    win32_error_block,
                    unhandled_request_block,
                )

                self.builder.position_at_end(unhandled_request_block)
                unhandled_format = self.visit_LiteralNode(
                    LiteralNode(
                        "str",
                        "Error: the window thread did not handle interface '%s' in window '%s'\n",
                    )
                )[0]
                unhandled_interface_name = self.visit_LiteralNode(
                    LiteralNode("str", key[1])
                )[0]
                self.builder.call(
                    self.printf_function,
                    [unhandled_format, unhandled_interface_name, window_title],
                )
                self.builder.branch(merge_block)
                unhandled_predecessor = self.builder.block

                self.builder.position_at_end(win32_error_block)
                error_format = self.visit_LiteralNode(
                    LiteralNode(
                        "str",
                        "Error: could not create interface '%s' in window '%s' (Windows error %d)\n",
                    )
                )[0]
                interface_name = self.visit_LiteralNode(
                    LiteralNode("str", key[1])
                )[0]
                interface_name = self.visit_LiteralNode(
                    LiteralNode("str", key[1])
                )[0]
                self.builder.call(
                    self.printf_function,
                    [error_format, interface_name, window_title, error_code],
                )
                self.builder.branch(merge_block)
                failure_predecessor = self.builder.block

                self.builder.position_at_end(created_block)
                self.builder.branch(merge_block)
                success_predecessor = self.builder.block

                self.builder.position_at_end(merge_block)
                res = self.builder.phi(self.bool_type, name="interface_create_result")
                res.add_incoming(
                    ir.Constant(self.bool_type, 0),
                    missing_parent_predecessor,
                )
                res.add_incoming(
                    ir.Constant(self.bool_type, 0),
                    unhandled_predecessor,
                )
                res.add_incoming(ir.Constant(self.bool_type, 0), failure_predecessor)
                res.add_incoming(ir.Constant(self.bool_type, 1), success_predecessor)
                return res, "bool"
            if node.method_name == "Interface_Clicked":
                self.require_argument_count(node, 2)
                control_id = self.get_interface_id(
                    node.arguments[0],
                    node.arguments[1],
                    "button",
                )
                if self.interface_clicked_global is None:
                    self.get_window_runtime_functions()
                self.emit_interface_message_pump()
                click_flag_pointer = self.builder.gep(
                    self.interface_clicked_global,
                    [
                        ir.Constant(self.int32_type, 0),
                        ir.Constant(self.int32_type, control_id),
                    ],
                    name="interface_click_flag",
                )
                clicked_id = self.builder.atomic_rmw(
                    "xchg",
                    click_flag_pointer,
                    ir.Constant(self.int32_type, 0),
                    "acquire",
                    name="interface_click_result",
                )
                return self.builder.icmp_signed(
                    "!=",
                    clicked_id,
                    ir.Constant(self.int32_type, 0),
                    name="interface_was_clicked",
                ), "bool"
            if node.method_name == "Get_Interface_Text":
                self.require_argument_count(node, 2)
                control_id = self.get_interface_id(
                    node.arguments[0],
                    node.arguments[1],
                    "editable",
                )
                key = self.get_interface_key(node.arguments[0], node.arguments[1])
                window_title = self.visit_LiteralNode(LiteralNode("str", key[0]))[0]
                self.emit_interface_message_pump()
                parent_window = self.builder.call(
                    self.find_window_function,
                    [ir.Constant(self.char_pointer_type, None), window_title],
                    name="interface_text_parent",
                )
                control_window = self.builder.call(
                    self.get_dialog_item_function,
                    [
                        parent_window,
                        ir.Constant(self.int32_type, control_id),
                    ],
                    name="interface_text_control",
                )
                fn = self.builder.function
                missing_block = fn.append_basic_block(name="interface_text_missing")
                read_block = fn.append_basic_block(name="interface_text_read")
                merge_block = fn.append_basic_block(name="interface_text_end")
                control_missing = self.builder.icmp_unsigned(
                    "==",
                    control_window,
                    ir.Constant(self.char_pointer_type, None),
                )
                self.builder.cbranch(control_missing, missing_block, read_block)

                self.builder.position_at_end(missing_block)
                error_format = self.visit_LiteralNode(
                    LiteralNode(
                        "str",
                        "Error: interface '%s' was not found in window '%s'\\n",
                    )
                )[0]
                name_value = self.visit_LiteralNode(LiteralNode("str", key[1]))[0]
                self.builder.call(
                    self.printf_function,
                    [error_format, name_value, window_title],
                )
                empty_text = self.builder.call(
                    self.malloc_function,
                    [ir.Constant(self.int64_type, 1)],
                    name="missing_interface_text",
                )
                self.builder.store(
                    ir.Constant(ir.IntType(8), 0),
                    empty_text,
                )
                self.builder.branch(merge_block)
                missing_predecessor = self.builder.block

                self.builder.position_at_end(read_block)
                text_length = self.builder.call(
                    self.get_window_text_length_function,
                    [control_window],
                    name="interface_text_length",
                )
                allocation_size = self.builder.zext(text_length, self.int64_type)
                allocation_size = self.builder.add(
                    allocation_size,
                    ir.Constant(self.int64_type, 1),
                )
                text_buffer = self.builder.call(
                    self.malloc_function,
                    [allocation_size],
                    name="interface_text_buffer",
                )
                self.builder.call(
                    self.get_window_text_function,
                    [
                        control_window,
                        text_buffer,
                        self.builder.trunc(allocation_size, self.int32_type),
                    ],
                )
                self.builder.branch(merge_block)
                read_predecessor = self.builder.block

                self.builder.position_at_end(merge_block)
                res = self.builder.phi(self.char_pointer_type, name="interface_text_result")
                res.add_incoming(empty_text, missing_predecessor)
                res.add_incoming(text_buffer, read_predecessor)
                return res, "str"
            if node.method_name == "Launch_Window":
                executable_path = self.get_process_name_argument(node)
                operation = self.visit_LiteralNode(LiteralNode("str", "open"))[0]
                null_pointer = ir.Constant(self.char_pointer_type, None)
                launch_result = self.builder.call(
                    self.shell_execute_function,
                    [
                        null_pointer,
                        operation,
                        executable_path,
                        null_pointer,
                        null_pointer,
                        ir.Constant(self.int32_type, 1),
                    ],
                    name="launched_executable",
                )
                launch_succeeded = self.builder.icmp_unsigned(
                    ">",
                    launch_result,
                    ir.Constant(self.int64_type, 32).inttoptr(self.char_pointer_type),
                    name="executable_launch_succeeded",
                )
                fn = self.builder.function
                success_block = fn.append_basic_block(name="executable_launch_success")
                error_block = fn.append_basic_block(name="executable_launch_error")
                merge_block = fn.append_basic_block(name="executable_launch_end")
                self.builder.cbranch(launch_succeeded, success_block, error_block)

                self.builder.position_at_end(error_block)
                error_code = self.builder.trunc(
                    self.builder.ptrtoint(launch_result, self.int64_type),
                    self.int32_type,
                    name="executable_launch_error_code",
                )
                error_format = self.visit_LiteralNode(
                    LiteralNode("str", "Error: could not launch executable '%s' (code %d)\n")
                )[0]
                self.builder.call(
                    self.printf_function,
                    [error_format, executable_path, error_code],
                )
                self.builder.branch(merge_block)
                error_predecessor = self.builder.block

                self.builder.position_at_end(success_block)
                self.builder.branch(merge_block)
                success_predecessor = self.builder.block

                self.builder.position_at_end(merge_block)
                launched = self.builder.phi(self.bool_type, name="executable_launch_result")
                launched.add_incoming(ir.Constant(self.bool_type, 0), error_predecessor)
                launched.add_incoming(ir.Constant(self.bool_type, 1), success_predecessor)
                return launched, "bool"
            if node.method_name in ("Remove_Window", "Get_Window", "List_Windows"):
                if node.method_name == "List_Windows":
                    self.require_argument_count(node, 0)
                    title = ir.Constant(self.char_pointer_type, None)
                    operation = 3
                else:
                    title = self.get_process_name_argument(node)
                    operation = 2 if node.method_name == "Remove_Window" else 1

                window_operation = self.get_window_operation_function()
                cnt = self.builder.call(
                    window_operation,
                    [ir.Constant(self.int32_type, operation), title],
                    name=f"{node.method_name.lower()}_count",
                )
                if node.method_name == "List_Windows":
                    return cnt, "int"

                succeeded = self.builder.icmp_signed(
                    ">",
                    cnt,
                    ir.Constant(self.int32_type, 0),
                    name=f"{node.method_name.lower()}_succeeded",
                )
                return succeeded, "bool"

        raise NotImplementedError(f"Method '{node.library_name}.{node.method_name}' is not implemented.")

    def require_argument_count(self, node, expected_count):
        if len(node.arguments) != expected_count:
            raise TypeError(
                f"{node.library_name}.{node.method_name} expects "
                f"{expected_count} argument(s), got {len(node.arguments)}"
            )

    def get_interface_key(self, window_expression, name_expression):
        if not isinstance(window_expression, LiteralNode) or window_expression.literal_type != "str":
            raise TypeError("Interface window title must be a string literal")
        if not isinstance(name_expression, LiteralNode) or name_expression.literal_type != "str":
            raise TypeError("Interface name must be a string literal")
        return window_expression.value, name_expression.value

    def get_interface_request_type(self):
        if self.interface_request_type is None:
            self.interface_request_type = ir.LiteralStructType(
                [
                    self.char_pointer_type,
                    self.char_pointer_type,
                    *([self.int32_type] * 13),
                    self.char_pointer_type,
                    self.char_pointer_type,
                    self.int32_type,
                    self.int32_type,
                ]
            )
        return self.interface_request_type

    def reserve_interface_id(self, key):
        info = self.interface_ids.get(key)
        if info is not None:
            return info["id"]
        self.interface_id_count += 1
        if self.interface_id_count > 0xffff:
            raise ValueError("A program cannot declare or query more than 65535 interfaces")
        self.interface_ids[key] = {
            "id": self.interface_id_count,
            "type": None,
            "editable": False,
            "declared": False,
            "requested_types": [],
        }
        return self.interface_id_count

    def register_interface(self, key, interface_type, editable=False):
        control_id = self.reserve_interface_id(key)
        existing = self.interface_ids.get(key)
        if existing is not None and existing["declared"]:
            raise SyntaxError(
                f"Interface name '{key[1]}' is already used for window '{key[0]}'"
            )
        if existing is not None:
            for want_ty in existing.get("requested_types", []):
                if want_ty == "editable":
                    if interface_type != "label" or not editable:
                        raise TypeError(
                            f"Interface '{key[1]}' is not an editable text field"
                        )
                elif want_ty != interface_type:
                    raise TypeError(
                        f"Interface '{key[1]}' must be a {want_ty}, "
                        f"not a {interface_type}"
                    )
        self.interface_ids[key] = {
            "id": control_id,
            "type": interface_type,
            "editable": editable,
            "declared": True,
            "requested_types": (
                existing.get("requested_types", []) if existing is not None else []
            ),
        }
        return control_id

    def get_interface_id(self, window_expression, name_expression, expected_type=None):
        key = self.get_interface_key(window_expression, name_expression)
        self.reserve_interface_id(key)
        info = self.interface_ids[key]
        if expected_type is not None and expected_type not in info["requested_types"]:
            info["requested_types"].append(expected_type)
        if expected_type == "editable":
            if info["declared"] and not info["editable"]:
                raise TypeError(f"Interface '{key[1]}' is not an editable text field")
        elif (
            info["declared"]
            and expected_type is not None
            and info["type"] != expected_type
        ):
            raise TypeError(
                f"Interface '{key[1]}' must be a {expected_type}, "
                f"not a {info['type']}"
            )
        return info["id"]

    @staticmethod
    def parse_interface_color(expression, property_name):
        if not isinstance(expression, LiteralNode) or expression.literal_type != "str":
            raise TypeError(f"Interface property '{property_name}' must be a '#RRGGBB' string")
        color = expression.value
        if len(color) != 7 or color[0] != "#":
            raise ValueError(
                f"Interface property '{property_name}' must use '#RRGGBB' format"
            )
        try:
            red = int(color[1:3], 16)
            green = int(color[3:5], 16)
            blue = int(color[5:7], 16)
        except ValueError as error:
            raise ValueError(
                f"Interface property '{property_name}' must use '#RRGGBB' format"
            ) from error
        return (blue << 16) | (green << 8) | red

    @staticmethod
    def blend_color(foreground, background, opacity):
        channels = []
        for shift in (0, 8, 16):
            src = (foreground >> shift) & 0xff
            target = (background >> shift) & 0xff
            channels.append(round(src * opacity + target * (1.0 - opacity)))
        return channels[0] | (channels[1] << 8) | (channels[2] << 16)

    def emit_interface_message_pump(self):
        if self.interface_message_pump_function is None:
            fn = ir.Function(
                self.module,
                ir.FunctionType(ir.VoidType(), []),
                name="vamp_pump_interface_messages",
            )
            fn.linkage = "internal"
            entry_block = fn.append_basic_block(name="entry")
            check_block = fn.append_basic_block(name="check")
            dispatch_block = fn.append_basic_block(name="dispatch")
            finish_block = fn.append_basic_block(name="finish")
            pump_builder = ir.IRBuilder(entry_block)

            message_type = ir.LiteralStructType(
                [
                    self.char_pointer_type,
                    self.int32_type,
                    self.int64_type,
                    self.int64_type,
                    self.int32_type,
                    ir.ArrayType(self.int32_type, 2),
                ]
            )
            msg = pump_builder.alloca(message_type, name="interface_message")
            message_bytes = pump_builder.bitcast(msg, self.char_pointer_type)
            pump_builder.branch(check_block)
            pump_builder.position_at_end(check_block)
            has_message = pump_builder.call(
                self.peek_message_function,
                [
                    message_bytes,
                    ir.Constant(self.char_pointer_type, None),
                    ir.Constant(self.int32_type, 0),
                    ir.Constant(self.int32_type, 0),
                    ir.Constant(self.int32_type, 1),
                ],
            )
            pump_builder.cbranch(
                pump_builder.icmp_signed(
                    "!=",
                    has_message,
                    ir.Constant(self.int32_type, 0),
                ),
                dispatch_block,
                finish_block,
            )
            pump_builder.position_at_end(dispatch_block)
            pump_builder.call(self.translate_message_function, [message_bytes])
            pump_builder.call(self.dispatch_message_function, [message_bytes])
            pump_builder.branch(check_block)
            pump_builder.position_at_end(finish_block)
            pump_builder.ret_void()
            self.interface_message_pump_function = fn

        self.builder.call(self.interface_message_pump_function, [])

    def get_interface_parent_function(self):
        if self.interface_parent_function is not None:
            return self.interface_parent_function

        context_type = ir.LiteralStructType(
            [self.char_pointer_type, self.char_pointer_type]
        )
        callback_type = ir.FunctionType(
            self.int32_type,
            [self.char_pointer_type, self.int64_type],
        )
        callback = ir.Function(
            self.module,
            callback_type,
            name="vamp_find_interface_parent_callback",
        )
        callback.linkage = "internal"
        callback.args[0].name = "candidate_window"
        callback.args[1].name = "context"
        callback_entry = callback.append_basic_block(name="entry")
        title_block = callback.append_basic_block(name="check_title")
        compare_block = callback.append_basic_block(name="compare_title")
        found_block = callback.append_basic_block(name="found")
        continue_block = callback.append_basic_block(name="continue")
        callback_builder = ir.IRBuilder(callback_entry)
        ctx = callback_builder.inttoptr(
            callback.args[1],
            context_type.as_pointer(),
        )
        process_id_pointer = callback_builder.alloca(
            self.int32_type,
            name="candidate_process_id",
        )
        callback_builder.call(
            self.get_window_thread_process_id_function,
            [callback.args[0], process_id_pointer],
        )
        candidate_process_id = callback_builder.load(process_id_pointer)
        current_process_id = callback_builder.call(
            self.get_current_process_id_function,
            [],
        )
        is_own_process = callback_builder.icmp_signed(
            "==",
            candidate_process_id,
            current_process_id,
        )
        callback_builder.cbranch(is_own_process, title_block, continue_block)

        callback_builder.position_at_end(title_block)
        title_buffer_type = ir.ArrayType(self.int32_type, 128)
        title_buffer = callback_builder.alloca(title_buffer_type, name="candidate_title")
        title_pointer = callback_builder.bitcast(
            title_buffer,
            self.char_pointer_type,
        )
        title_length = callback_builder.call(
            self.get_window_text_function,
            [
                callback.args[0],
                title_pointer,
                ir.Constant(self.int32_type, 512),
            ],
        )
        has_title = callback_builder.icmp_signed(
            ">",
            title_length,
            ir.Constant(self.int32_type, 0),
        )
        callback_builder.cbranch(has_title, compare_block, continue_block)

        callback_builder.position_at_end(compare_block)
        wanted_title_pointer = callback_builder.gep(
            ctx,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 0)],
        )
        wanted_title = callback_builder.load(wanted_title_pointer)
        title_matches = callback_builder.call(
            self.compare_case_insensitive_function,
            [title_pointer, wanted_title],
        )
        is_match = callback_builder.icmp_signed(
            "==",
            title_matches,
            ir.Constant(self.int32_type, 0),
        )
        callback_builder.cbranch(is_match, found_block, continue_block)

        callback_builder.position_at_end(found_block)
        result_pointer = callback_builder.gep(
            ctx,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 1)],
        )
        callback_builder.store(callback.args[0], result_pointer)
        callback_builder.ret(ir.Constant(self.int32_type, 0))

        callback_builder.position_at_end(continue_block)
        callback_builder.ret(ir.Constant(self.int32_type, 1))

        fn = ir.Function(
            self.module,
            ir.FunctionType(self.char_pointer_type, [self.char_pointer_type]),
            name="vamp_find_interface_parent",
        )
        fn.linkage = "internal"
        fn.args[0].name = "title"
        entry = fn.append_basic_block(name="entry")
        builder = ir.IRBuilder(entry)
        context_pointer = builder.alloca(context_type, name="interface_parent_search")
        title_pointer = builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 0)],
        )
        result_pointer = builder.gep(
            context_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 1)],
        )
        builder.store(fn.args[0], title_pointer)
        builder.store(ir.Constant(self.char_pointer_type, None), result_pointer)
        builder.call(
            self.enum_windows_function,
            [
                builder.bitcast(callback, self.char_pointer_type),
                builder.ptrtoint(context_pointer, self.int64_type),
            ],
        )
        res = builder.load(result_pointer, name="interface_parent_window")
        builder.ret(res)
        self.interface_parent_function = fn
        return fn

    def emit_interface_layer_ordering_function(self):
        helper_type = ir.FunctionType(
            ir.VoidType(),
            [
                self.char_pointer_type,
                self.char_pointer_type,
                self.int32_type,
            ],
        )
        helper = ir.Function(
            self.module,
            helper_type,
            name="vamp_order_interface_control",
        )
        helper.linkage = "internal"
        parent, control, layer = helper.args
        entry = helper.append_basic_block(name="entry")
        inspect = helper.append_basic_block(name="inspect_sibling")
        compare = helper.append_basic_block(name="compare_sibling_layer")
        read_layer = helper.append_basic_block(name="read_sibling_layer")
        compare_layer = helper.append_basic_block(name="compare_interface_layers")
        save_anchor = helper.append_basic_block(name="save_layer_anchor")
        advance = helper.append_basic_block(name="advance_sibling")
        reorder = helper.append_basic_block(name="reorder_interface_control")
        builder = ir.IRBuilder(entry)
        sibling_pointer = builder.alloca(
            self.char_pointer_type,
            name="interface_sibling",
        )
        anchor_pointer = builder.alloca(
            self.char_pointer_type,
            name="interface_layer_anchor",
        )
        builder.store(
            builder.call(
                self.get_window_function,
                [parent, ir.Constant(self.int32_type, 5)],
            ),
            sibling_pointer,
        )
        builder.store(
            ir.Constant(self.char_pointer_type, None),
            anchor_pointer,
        )
        builder.branch(inspect)

        builder.position_at_end(inspect)
        sibling = builder.load(sibling_pointer)
        has_sibling = builder.icmp_unsigned(
            "!=",
            sibling,
            ir.Constant(self.char_pointer_type, None),
        )
        builder.cbranch(has_sibling, compare, reorder)

        builder.position_at_end(compare)
        is_control = builder.icmp_unsigned("==", sibling, control)
        builder.cbranch(is_control, advance, read_layer)

        builder.position_at_end(read_layer)
        encoded_sibling_layer = builder.call(
            self.get_property_function,
            [
                sibling,
                self.constant_string_pointer("vamp.interface.layer"),
            ],
        )
        has_layer = builder.icmp_unsigned(
            "!=",
            encoded_sibling_layer,
            ir.Constant(self.char_pointer_type, None),
        )
        builder.cbranch(has_layer, compare_layer, advance)

        builder.position_at_end(compare_layer)
        sibling_layer = builder.trunc(
            builder.sub(
                builder.ptrtoint(encoded_sibling_layer, self.int64_type),
                ir.Constant(self.int64_type, 2147483649),
            ),
            self.int32_type,
        )
        is_higher_layer = builder.icmp_signed(">", sibling_layer, layer)
        builder.cbranch(is_higher_layer, save_anchor, advance)

        builder.position_at_end(save_anchor)
        builder.store(sibling, anchor_pointer)
        builder.branch(advance)

        builder.position_at_end(advance)
        next_sibling = builder.call(
            self.get_window_function,
            [sibling, ir.Constant(self.int32_type, 2)],
        )
        builder.store(next_sibling, sibling_pointer)
        builder.branch(inspect)

        builder.position_at_end(reorder)
        anchor = builder.load(anchor_pointer)
        has_higher_layer = builder.icmp_unsigned(
            "!=",
            anchor,
            ir.Constant(self.char_pointer_type, None),
        )
        insert_after = builder.select(
            has_higher_layer,
            anchor,
            builder.inttoptr(
                ir.Constant(self.int64_type, 0),
                self.char_pointer_type,
            ),
        )
        builder.call(
            self.set_window_pos_function,
            [
                control,
                insert_after,
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0x0013),
            ],
        )
        builder.call(
            self.redraw_window_function,
            [
                parent,
                ir.Constant(self.char_pointer_type, None),
                ir.Constant(self.char_pointer_type, None),
                ir.Constant(self.int32_type, 0x0185),
            ],
        )
        builder.ret_void()
        return helper

    def emit_interface_creation_function(self, function):
        order_interfaces = self.emit_interface_layer_ordering_function()
        entry = function.append_basic_block(name="entry")
        creation_failed = function.append_basic_block(name="creation_failed")
        created = function.append_basic_block(name="created")
        configure_background = function.append_basic_block(name="configure_background")
        configure_text_color = function.append_basic_block(name="configure_text_color")
        configure_font = function.append_basic_block(name="configure_font")
        configure_icon = function.append_basic_block(name="configure_icon")
        load_icon_block = function.append_basic_block(name="load_icon")
        show_control = function.append_basic_block(name="show_control")
        builder = ir.IRBuilder(entry)
        request = function.args[1]
        def load_field(index, name):
            field_pointer = builder.gep(
                request,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, index)],
                name=f"{name}_pointer",
            )
            return builder.load(field_pointer, name=name)

        cls_name = load_field(0, "interface_class")
        text = load_field(1, "interface_text")
        style = load_field(2, "interface_style")
        x_position = load_field(3, "interface_x")
        y_position = load_field(4, "interface_y")
        width = load_field(5, "interface_width")
        height = load_field(6, "interface_height")
        control_id = load_field(7, "interface_id")
        ex_style = load_field(8, "interface_ex_style")
        layer = load_field(9, "interface_layer")
        visible = load_field(10, "interface_visible")
        text_color = load_field(11, "interface_text_color")
        background_mode = load_field(12, "interface_background_mode")
        background_color = load_field(13, "interface_background_color")
        font_size = load_field(14, "interface_font_size")
        font_name = load_field(15, "interface_font_name")
        icon_path = load_field(16, "interface_icon_path")
        icon_kind = load_field(17, "interface_icon_kind")
        error_pointer = builder.gep(
            request,
            [
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 18),
            ],
            name="interface_error_pointer",
        )
        null_pointer = ir.Constant(self.char_pointer_type, None)

        module_handle = builder.call(
            self.get_module_handle_function,
            [null_pointer],
        )
        builder.call(
            self.set_last_error_function,
            [ir.Constant(self.int32_type, 0)],
        )
        control = builder.call(
            self.create_window_function,
            [
                ex_style,
                cls_name,
                text,
                style,
                x_position,
                y_position,
                width,
                height,
                function.args[0],
                builder.inttoptr(control_id, self.char_pointer_type),
                module_handle,
                null_pointer,
            ],
            name="created_interface_control",
        )
        control_created = builder.icmp_unsigned("!=", control, null_pointer)
        builder.cbranch(control_created, created, creation_failed)

        builder.position_at_end(creation_failed)
        builder.store(builder.call(self.get_last_error_function, []), error_pointer)
        builder.ret(null_pointer)
        builder.position_at_end(created)
        encoded_layer = builder.add(
            builder.sext(layer, self.int64_type),
            ir.Constant(self.int64_type, 2147483649),
        )
        builder.call(
            self.set_property_function,
            [
                control,
                self.constant_string_pointer("vamp.interface.layer"),
                builder.inttoptr(encoded_layer, self.char_pointer_type),
            ],
        )
        has_text_color = builder.icmp_unsigned(
            "!=",
            text_color,
            ir.Constant(self.int32_type, 0),
        )
        builder.cbranch(
            has_text_color,
            configure_text_color,
            configure_background,
        )

        builder.position_at_end(configure_text_color)
        builder.call(
            self.set_property_function,
            [
                control,
                self.constant_string_pointer("vamp.text.color"),
                builder.inttoptr(text_color, self.char_pointer_type),
            ],
        )
        builder.branch(configure_background)

        background_transparent = function.append_basic_block(name="background_transparent")
        background_colored = function.append_basic_block(name="background_colored")
        background_ready = function.append_basic_block(name="background_ready")
        builder.position_at_end(configure_background)
        is_transparent = builder.icmp_signed(
            "==",
            background_mode,
            ir.Constant(self.int32_type, 1),
        )
        builder.cbranch(is_transparent, background_transparent, background_colored)

        builder.position_at_end(background_transparent)
        builder.call(
            self.set_property_function,
            [
                control,
                self.constant_string_pointer("vamp.background.transparent"),
                ir.Constant(self.int32_type, 1).inttoptr(self.char_pointer_type),
            ],
        )
        builder.branch(background_ready)

        builder.position_at_end(background_colored)
        has_background_color = builder.icmp_signed(
            ">",
            background_mode,
            ir.Constant(self.int32_type, 1),
        )
        create_brush_block = function.append_basic_block(name="create_background_brush")
        builder.cbranch(has_background_color, create_brush_block, background_ready)

        builder.position_at_end(create_brush_block)
        brush = builder.call(
            self.create_solid_brush_function,
            [background_color],
            name="interface_background_brush",
        )
        builder.call(
            self.set_property_function,
            [
                control,
                self.constant_string_pointer("vamp.background.brush"),
                brush,
            ],
        )
        builder.call(
            self.set_property_function,
            [
                control,
                self.constant_string_pointer("vamp.background.color"),
                builder.inttoptr(
                    builder.add(background_color, ir.Constant(self.int32_type, 1)),
                    self.char_pointer_type,
                ),
            ],
        )
        has_background_opacity = builder.icmp_signed(
            ">",
            background_mode,
            ir.Constant(self.int32_type, 2),
        )
        set_background_opacity_block = function.append_basic_block(
            name="set_background_opacity"
        )
        builder.cbranch(
            has_background_opacity,
            set_background_opacity_block,
            background_ready,
        )
        builder.position_at_end(set_background_opacity_block)
        encoded_opacity = builder.add(
            builder.sub(background_mode, ir.Constant(self.int32_type, 3)),
            ir.Constant(self.int32_type, 1),
        )
        builder.call(
            self.set_property_function,
            [
                control,
                self.constant_string_pointer("vamp.background.opacity"),
                builder.inttoptr(encoded_opacity, self.char_pointer_type),
            ],
        )
        builder.branch(background_ready)

        builder.position_at_end(background_ready)
        requested_font_size = builder.icmp_signed(
            ">",
            font_size,
            ir.Constant(self.int32_type, 0),
        )
        builder.cbranch(requested_font_size, configure_font, configure_icon)

        builder.position_at_end(configure_font)
        font = builder.call(
            self.create_font_function,
            [
                builder.neg(font_size),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 400),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 1),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                ir.Constant(self.int32_type, 0),
                font_name,
            ],
            name="interface_font",
        )
        font_created = builder.icmp_unsigned("!=", font, null_pointer)
        font_ready = function.append_basic_block(name="font_ready")
        font_failed = function.append_basic_block(name="font_failed")
        builder.cbranch(font_created, font_ready, font_failed)

        builder.position_at_end(font_failed)
        builder.store(builder.call(self.get_last_error_function, []), error_pointer)
        builder.call(self.destroy_window_function, [control])
        builder.ret(null_pointer)

        builder.position_at_end(font_ready)
        builder.call(
            self.send_message_function,
            [
                control,
                ir.Constant(self.int32_type, 0x0030),
                builder.ptrtoint(font, self.int64_type),
                ir.Constant(self.int64_type, 1),
            ],
        )
        builder.branch(configure_icon)

        builder.position_at_end(configure_icon)
        icon_requested = builder.icmp_unsigned("!=", icon_path, null_pointer)
        skip_icon_block = function.append_basic_block(name="skip_interface_icon")
        builder.cbranch(icon_requested, load_icon_block, skip_icon_block)

        builder.position_at_end(load_icon_block)
        icon = builder.call(
            self.get_window_icon_function(),
            [icon_path],
            name="interface_icon",
        )
        has_icon = builder.icmp_unsigned("!=", icon, null_pointer)
        use_icon_block = function.append_basic_block(name="set_interface_icon")
        icon_failed = function.append_basic_block(name="interface_icon_failed")
        builder.cbranch(
            has_icon,
            use_icon_block,
            icon_failed,
        )

        builder.position_at_end(icon_failed)
        builder.store(ir.Constant(self.int32_type, 2), error_pointer)
        builder.call(self.destroy_window_function, [control])
        builder.ret(null_pointer)

        builder.position_at_end(use_icon_block)
        builder.call(
            self.set_property_function,
            [
                control,
                self.constant_string_pointer("vamp.interface.icon"),
                ir.Constant(self.int32_type, 1).inttoptr(self.char_pointer_type),
            ],
        )
        icon_message = builder.select(
            builder.icmp_signed(
                "==",
                icon_kind,
                ir.Constant(self.int32_type, 1),
            ),
            ir.Constant(self.int32_type, 0x00F7),
            ir.Constant(self.int32_type, 0x0172),
        )
        builder.call(
            self.send_message_function,
            [
                control,
                icon_message,
                ir.Constant(self.int64_type, 1),
                builder.ptrtoint(icon, self.int64_type),
            ],
        )
        builder.branch(skip_icon_block)

        builder.position_at_end(skip_icon_block)
        builder.branch(show_control)

        builder.position_at_end(show_control)
        is_visible = builder.icmp_signed(
            "!=",
            visible,
            ir.Constant(self.int32_type, 0),
        )
        builder.call(
            self.show_window_function,
            [
                control,
                builder.select(
                    is_visible,
                    ir.Constant(self.int32_type, 5),
                    ir.Constant(self.int32_type, 0),
                ),
            ],
        )
        builder.call(self.update_window_function, [control])
        builder.call(
            order_interfaces,
            [function.args[0], control, layer],
        )
        builder.ret(control)

    def get_directory_path_argument(self, node):
        self.require_argument_count(node, 1)
        path_value, path_type = self.visit(node.arguments[0])
        if path_type != "str":
            raise TypeError(
                f"{node.library_name}.{node.method_name} expected string path"
            )
        return path_value

    def get_process_name_argument(self, node):
        self.require_argument_count(node, 1)
        process_name, process_name_type = self.visit(node.arguments[0])
        if process_name_type != "str":
            raise TypeError(
                f"{node.library_name}.{node.method_name} expected a program name string"
            )
        return process_name

    def emit_absolute_path(self, path_value):
        fn = self.builder.function
        max_windows_path_length = 32768
        path_buffer = self.allocate_bytes(
            ir.Constant(self.int32_type, max_windows_path_length),
            name="absolute_directory_path_buffer",
        )
        null_pointer = ir.Constant(self.char_pointer_type, None)
        null_file_part_pointer = ir.Constant(
            self.char_pointer_type.as_pointer(),
            None,
        )
        empty_path = self.allocate_bytes(
            ir.Constant(self.int32_type, 1),
            name="empty_path_buffer",
        )
        self.builder.store(ir.Constant(ir.IntType(8), 0), empty_path)

        resolved_length = self.builder.call(
            self.get_full_path_name_function,
            [
                path_value,
                ir.Constant(self.int32_type, max_windows_path_length),
                path_buffer,
                null_file_part_pointer,
            ],
            name="absolute_path_length",
        )
        path_resolved = self.builder.icmp_unsigned(
            "!=",
            resolved_length,
            ir.Constant(self.int32_type, 0),
        )
        path_fits_buffer = self.builder.icmp_unsigned(
            "<",
            resolved_length,
            ir.Constant(self.int32_type, max_windows_path_length),
        )
        path_is_resolved = self.builder.and_(path_resolved, path_fits_buffer)
        resolve_error_block = fn.append_basic_block(name="absolute_path_error")
        success_block = fn.append_basic_block(name="absolute_path_success")
        merge_block = fn.append_basic_block(name="absolute_path_end")
        self.builder.cbranch(path_is_resolved, success_block, resolve_error_block)

        self.builder.position_at_end(resolve_error_block)
        resolve_error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not resolve absolute path for '%s'\n")
        )[0]
        self.builder.call(self.printf_function, [resolve_error_format, path_value])
        self.builder.call(self.free_function, [path_buffer])
        self.builder.branch(merge_block)
        resolve_error_predecessor = self.builder.block

        self.builder.position_at_end(success_block)
        self.builder.branch(merge_block)
        success_predecessor = self.builder.block

        self.builder.position_at_end(merge_block)
        res = self.builder.phi(self.char_pointer_type, name="absolute_path")
        res.add_incoming(empty_path, resolve_error_predecessor)
        res.add_incoming(path_buffer, success_predecessor)
        return res, "str"

    def emit_absolute_directory_path(self, path_value):
        fn = self.builder.function
        empty_path = self.allocate_bytes(
            ir.Constant(self.int32_type, 1),
            name="empty_directory_path_buffer",
        )
        self.builder.store(ir.Constant(ir.IntType(8), 0), empty_path)
        attributes = self.builder.call(self.get_file_attributes_function, [path_value])
        invalid_attributes = self.builder.icmp_signed(
            "==",
            attributes,
            ir.Constant(self.int32_type, -1),
        )
        is_directory = self.builder.icmp_unsigned(
            "!=",
            self.builder.and_(attributes, ir.Constant(self.int32_type, 0x10)),
            ir.Constant(self.int32_type, 0),
        )
        invalid_path = self.builder.or_(invalid_attributes, self.builder.not_(is_directory))
        invalid_block = fn.append_basic_block(name="get_directory_invalid")
        resolve_block = fn.append_basic_block(name="get_directory_resolve")
        merge_block = fn.append_basic_block(name="get_directory_end")
        self.builder.cbranch(invalid_path, invalid_block, resolve_block)

        self.builder.position_at_end(invalid_block)
        error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: directory does not exist: '%s'\n")
        )[0]
        self.builder.call(self.printf_function, [error_format, path_value])
        self.builder.branch(merge_block)
        invalid_predecessor = self.builder.block

        self.builder.position_at_end(resolve_block)
        absolute_path, _ = self.emit_absolute_path(path_value)
        self.builder.branch(merge_block)
        resolve_predecessor = self.builder.block

        self.builder.position_at_end(merge_block)
        res = self.builder.phi(self.char_pointer_type, name="absolute_directory_path")
        res.add_incoming(empty_path, invalid_predecessor)
        res.add_incoming(absolute_path, resolve_predecessor)
        return res, "str"

    def emit_directory_removal(self, path_value):
        null_pointer = ir.Constant(self.char_pointer_type, None)
        path_length = self.builder.call(self.strlen_function, [path_value])
        buffer_size = self.builder.add(path_length, ir.Constant(self.int32_type, 2))
        double_null_path = self.allocate_bytes(
            buffer_size,
            name="remove_directory_path_buffer",
        )
        self.builder.call(self.strcpy_function, [double_null_path, path_value])
        second_null_pointer = self.builder.gep(
            double_null_path,
            [
                self.builder.add(
                    path_length,
                    ir.Constant(self.int32_type, 1),
                )
            ],
            name="remove_directory_path_terminator",
        )
        self.builder.store(ir.Constant(ir.IntType(8), 0), second_null_pointer)

        attributes = self.builder.call(self.get_file_attributes_function, [path_value])
        invalid_attributes = self.builder.icmp_signed(
            "==",
            attributes,
            ir.Constant(self.int32_type, -1),
        )
        is_directory = self.builder.icmp_unsigned(
            "!=",
            self.builder.and_(attributes, ir.Constant(self.int32_type, 0x10)),
            ir.Constant(self.int32_type, 0),
        )
        invalid_path = self.builder.or_(invalid_attributes, self.builder.not_(is_directory))

        fn = self.builder.function
        invalid_block = fn.append_basic_block(name="remove_directory_invalid")
        remove_block = fn.append_basic_block(name="remove_directory_operation")
        merge_block = fn.append_basic_block(name="remove_directory_end")
        self.builder.cbranch(invalid_path, invalid_block, remove_block)

        self.builder.position_at_end(invalid_block)
        error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: not a directory or it does not exist: '%s'\n")
        )[0]
        self.builder.call(self.printf_function, [error_format, path_value])
        self.builder.call(self.free_function, [double_null_path])
        self.builder.branch(merge_block)
        invalid_predecessor = self.builder.block

        self.builder.position_at_end(remove_block)
        file_operation = self.builder.alloca(
            self.file_operation_type,
            name="remove_directory_file_operation",
        )
        delete_operation = ir.Constant(self.int32_type, 3)
        silent_delete_flags = ir.Constant(ir.IntType(16), 0x414)
        fields = [
            null_pointer,
            delete_operation,
            double_null_path,
            null_pointer,
            silent_delete_flags,
            ir.Constant(self.int32_type, 0),
            null_pointer,
            null_pointer,
        ]
        for idx, value in enumerate(fields):
            field_pointer = self.builder.gep(
                file_operation,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)],
            )
            self.builder.store(value, field_pointer)

        res = self.builder.call(
            self.file_operation_function,
            [file_operation],
            name="remove_directory_result",
        )
        self.builder.call(self.free_function, [double_null_path])
        operation_succeeded = self.builder.icmp_signed(
            "==",
            res,
            ir.Constant(self.int32_type, 0),
        )
        error_block = fn.append_basic_block(name="remove_directory_error")
        success_block = fn.append_basic_block(name="remove_directory_success")
        self.builder.cbranch(operation_succeeded, success_block, error_block)

        self.builder.position_at_end(error_block)
        error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not remove directory '%s' (code %d)\n")
        )[0]
        self.builder.call(self.printf_function, [error_format, path_value, res])
        self.builder.branch(merge_block)
        error_predecessor = self.builder.block

        self.builder.position_at_end(success_block)
        self.builder.branch(merge_block)
        success_predecessor = self.builder.block

        self.builder.position_at_end(merge_block)
        succeeded = self.builder.phi(self.bool_type, name="remove_directory_succeeded")
        succeeded.add_incoming(ir.Constant(self.bool_type, 0), invalid_predecessor)
        succeeded.add_incoming(ir.Constant(self.bool_type, 0), error_predecessor)
        succeeded.add_incoming(ir.Constant(self.bool_type, 1), success_predecessor)
        return succeeded, "bool"

    def emit_directory_listing(self, path_value):
        fn = self.builder.function
        directory_attribute = ir.Constant(self.int32_type, 0x10)
        # FindFirstFileA writes the Windows WIN32_FIND_DATAA structure here.
        find_data_size = 592
        file_name_offset = 44

        attributes = self.builder.call(self.get_file_attributes_function, [path_value])
        invalid_attributes = self.builder.icmp_signed(
            "==",
            attributes,
            ir.Constant(self.int32_type, -1),
        )
        is_directory = self.builder.icmp_unsigned(
            "!=",
            self.builder.and_(attributes, directory_attribute),
            ir.Constant(self.int32_type, 0),
        )
        invalid_path = self.builder.or_(invalid_attributes, self.builder.not_(is_directory))

        error_block = fn.append_basic_block(name="directory_listing_error")
        search_block = fn.append_basic_block(name="directory_listing_search")
        empty_block = fn.append_basic_block(name="directory_listing_empty")
        empty_success_block = fn.append_basic_block(name="directory_listing_empty_success")
        search_error_block = fn.append_basic_block(name="directory_listing_search_error")
        entry_block = fn.append_basic_block(name="directory_listing_entry")
        next_block = fn.append_basic_block(name="directory_listing_next")
        next_error_check_block = fn.append_basic_block(name="directory_listing_next_error_check")
        iteration_error_block = fn.append_basic_block(name="directory_listing_iteration_error")
        print_block = fn.append_basic_block(name="directory_listing_print")
        skip_block = fn.append_basic_block(name="directory_listing_skip")
        close_block = fn.append_basic_block(name="directory_listing_close")
        merge_block = fn.append_basic_block(name="directory_listing_end")
        self.builder.cbranch(invalid_path, error_block, search_block)

        self.builder.position_at_end(error_block)
        error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: not a directory or it does not exist: '%s'\n")
        )[0]
        self.builder.call(self.printf_function, [error_format, path_value])
        self.builder.branch(merge_block)
        error_predecessor = self.builder.block

        self.builder.position_at_end(search_block)
        search_path_length = self.builder.call(self.strlen_function, [path_value])
        search_path_size = self.builder.add(
            search_path_length,
            ir.Constant(self.int32_type, 3),
        )
        search_path = self.allocate_bytes(search_path_size)
        self.builder.call(self.strcpy_function, [search_path, path_value])
        wildcard_suffix = self.visit_LiteralNode(LiteralNode("str", "\\*"))[0]
        self.builder.call(self.strcat_function, [search_path, wildcard_suffix])

        find_data_type = ir.ArrayType(ir.IntType(8), find_data_size)
        find_data = self.builder.alloca(find_data_type, name="directory_find_data")
        find_data_pointer = self.builder.bitcast(find_data, self.char_pointer_type)
        find_handle = self.builder.call(
            self.find_first_file_function,
            [search_path, find_data_pointer],
            name="directory_find_handle",
        )
        invalid_handle = ir.Constant(self.int64_type, -1).inttoptr(self.char_pointer_type)
        no_entries = self.builder.icmp_unsigned("==", find_handle, invalid_handle)
        count_pointer = self.builder.alloca(self.int32_type, name="directory_entry_count")
        self.builder.store(ir.Constant(self.int32_type, 0), count_pointer)
        iteration_failed_pointer = self.builder.alloca(
            self.int32_type,
            name="directory_iteration_failed",
        )
        self.builder.store(ir.Constant(self.int32_type, 0), iteration_failed_pointer)
        self.builder.cbranch(no_entries, empty_block, entry_block)

        self.builder.position_at_end(empty_block)
        search_error = self.builder.call(
            self.get_last_error_function,
            [],
            name="directory_listing_search_error_code",
        )
        no_matching_files = self.builder.icmp_unsigned(
            "==",
            search_error,
            ir.Constant(self.int32_type, 2),
        )
        self.builder.cbranch(no_matching_files, empty_success_block, search_error_block)

        self.builder.position_at_end(empty_success_block)
        self.builder.call(self.free_function, [search_path])
        self.builder.branch(merge_block)
        empty_predecessor = self.builder.block

        self.builder.position_at_end(search_error_block)
        search_error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not list directory '%s' (code %d)\n")
        )[0]
        self.builder.call(
            self.printf_function,
            [search_error_format, path_value, search_error],
        )
        self.builder.call(self.free_function, [search_path])
        self.builder.branch(merge_block)
        search_error_predecessor = self.builder.block

        self.builder.position_at_end(entry_block)
        file_name_pointer = self.builder.gep(
            find_data_pointer,
            [ir.Constant(self.int32_type, file_name_offset)],
            name="directory_entry_name",
        )
        current_name = file_name_pointer
        dot_name = self.visit_LiteralNode(LiteralNode("str", "."))[0]
        dot_dot_name = self.visit_LiteralNode(LiteralNode("str", ".."))[0]
        is_dot = self.builder.icmp_signed(
            "==",
            self.builder.call(self.strcmp_function, [current_name, dot_name]),
            ir.Constant(self.int32_type, 0),
        )
        is_dot_dot = self.builder.icmp_signed(
            "==",
            self.builder.call(self.strcmp_function, [current_name, dot_dot_name]),
            ir.Constant(self.int32_type, 0),
        )
        is_navigation_entry = self.builder.or_(is_dot, is_dot_dot)
        self.builder.cbranch(is_navigation_entry, skip_block, print_block)

        self.builder.position_at_end(print_block)
        line_format = self.visit_LiteralNode(LiteralNode("str", "%s\n"))[0]
        self.builder.call(self.printf_function, [line_format, current_name])
        cnt = self.builder.load(count_pointer, name="directory_entry_count_value")
        self.builder.store(
            self.builder.add(cnt, ir.Constant(self.int32_type, 1)),
            count_pointer,
        )
        self.builder.branch(next_block)

        self.builder.position_at_end(skip_block)
        self.builder.branch(next_block)

        self.builder.position_at_end(next_block)
        has_next_entry = self.builder.call(
            self.find_next_file_function,
            [find_handle, find_data_pointer],
            name="directory_has_next_entry",
        )
        has_next_entry = self.builder.icmp_signed(
            "!=",
            has_next_entry,
            ir.Constant(self.int32_type, 0),
        )
        self.builder.cbranch(has_next_entry, entry_block, next_error_check_block)

        self.builder.position_at_end(next_error_check_block)
        iteration_error = self.builder.call(
            self.get_last_error_function,
            [],
            name="directory_listing_iteration_error_code",
        )
        no_more_files = self.builder.icmp_unsigned(
            "==",
            iteration_error,
            ir.Constant(self.int32_type, 18),
        )
        self.builder.cbranch(no_more_files, close_block, iteration_error_block)

        self.builder.position_at_end(iteration_error_block)
        iteration_error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not continue listing directory '%s' (code %d)\n")
        )[0]
        self.builder.call(
            self.printf_function,
            [iteration_error_format, path_value, iteration_error],
        )
        self.builder.store(ir.Constant(self.int32_type, 1), iteration_failed_pointer)
        self.builder.branch(close_block)

        self.builder.position_at_end(close_block)
        self.builder.call(self.find_close_function, [find_handle])
        self.builder.call(self.free_function, [search_path])
        listed_count = self.builder.load(count_pointer, name="listed_directory_entry_count")
        iteration_failed = self.builder.load(
            iteration_failed_pointer,
            name="directory_iteration_failed_value",
        )
        listing_succeeded = self.builder.icmp_unsigned(
            "==",
            iteration_failed,
            ir.Constant(self.int32_type, 0),
        )
        listing_result = self.builder.select(
            listing_succeeded,
            listed_count,
            ir.Constant(self.int32_type, -1),
        )
        self.builder.branch(merge_block)
        close_predecessor = self.builder.block

        self.builder.position_at_end(merge_block)
        res = self.builder.phi(self.int32_type, name="directory_listing_result")
        res.add_incoming(ir.Constant(self.int32_type, -1), error_predecessor)
        res.add_incoming(ir.Constant(self.int32_type, 0), empty_predecessor)
        res.add_incoming(ir.Constant(self.int32_type, -1), search_error_predecessor)
        res.add_incoming(listing_result, close_predecessor)
        return res, "int"

    def visit_LiteralNode(self, node):
        if node.literal_type == "int":
            return ir.Constant(self.int32_type, node.value), "int"
        elif node.literal_type == "float":
            return ir.Constant(self.float_type, node.value), "float"
        elif node.literal_type == "bool":
            return ir.Constant(self.bool_type, 1 if node.value else 0), "bool"
        elif node.literal_type == "str":
            string_content = node.value + "\0"
            string_constant = ir.Constant(ir.ArrayType(ir.IntType(8), len(string_content)), bytearray(string_content.encode("utf-8")))
            self.string_literal_count += 1
            string_global = ir.GlobalVariable(self.module, string_constant.type, name=f".str_{self.string_literal_count}")
            string_global.linkage = "internal"
            string_global.initializer = string_constant
            return self.builder.bitcast(string_global, self.char_pointer_type), "str"

    def visit_ArrayLiteralNode(self, node):
        if not node.elements:
            raise TypeError("Arrays must contain at least one element so their type can be inferred")

        elems = []
        elem_ty = None
        for expr in node.elements:
            value, val_ty = self.visit(expr)
            if elem_ty is None:
                elem_ty = val_ty
            elif val_ty != elem_ty:
                raise TypeError("Array elements must all have the same type")
            elems.append(value)

        return ArrayLiteralValue(elems, elem_ty), "array"

    def visit_DictionaryLiteralNode(self, node):
        if not node.entries:
            raise TypeError("Dictionaries must contain at least one typed field")

        entries = []
        seen_keys = set()
        for key, decl_ty, expr in node.entries:
            if key in seen_keys:
                raise SyntaxError(f"Duplicate dictionary field '{key}'")
            seen_keys.add(key)
            value, val_ty = self.visit(expr)
            if val_ty != decl_ty:
                raise TypeError(f"Dictionary field '{key}' expects {decl_ty}, got {val_ty}")
            entries.append((key, decl_ty, value))

        return DictionaryLiteralValue(entries), "dictionary"

    def visit_VariableAccessNode(self, node):
        variable_type = self.type_information[node.variable_name]
        if (
            variable_type in ("array", "dictionary")
            or variable_type.startswith("class:")
        ):
            raise TypeError(f"Use an index or field to read '{node.variable_name}'")
        variable_pointer = self.variable_pointers[node.variable_name]
        value = self.builder.load(variable_pointer, name=f"{node.variable_name}_value")
        return value, variable_type

    def get_array_element_pointer(self, array, index_expression):
        if not isinstance(array, VariableAccessNode):
            raise TypeError("Indexed access requires an array or pointer variable")
        array_name = array.variable_name
        variable_type = self.type_information.get(array_name)
        idx, index_type = self.visit(index_expression)
        if index_type != "int":
            raise TypeError("Indexes must be int")

        if variable_type and variable_type.startswith("pointer:"):
            elem_ty = variable_type.removeprefix("pointer:")
            ptr = self.builder.load(
                self.variable_pointers[array_name],
                name=f"{array_name}_pointer_value",
            )
            return self.builder.gep(
                ptr,
                [idx],
                name=f"{array_name}_element_pointer",
            ), elem_ty

        if variable_type != "array":
            raise TypeError(f"'{array_name}' is not an array or pointer")
        array_info = self.array_information[array_name]
        return self.builder.gep(
            self.variable_pointers[array_name],
            [ir.Constant(self.int32_type, 0), idx],
            name=f"{array_name}_element_pointer",
        ), array_info["element_type"]

    def visit_ArrayAccessNode(self, node):
        element_pointer, elem_ty = self.get_array_element_pointer(
            node.array,
            node.index,
        )
        return self.builder.load(element_pointer, name="indexed_element"), elem_ty

    def visit_ArrayAssignmentNode(self, node):
        element_pointer, elem_ty = self.get_array_element_pointer(
            node.array,
            node.index,
        )
        value, val_ty = self.visit(node.expression)
        if node.operator != "=":
            if elem_ty != val_ty:
                raise TypeError(
                    f"Indexed assignment type mismatch: {elem_ty} and {val_ty}"
                )
            current_value = self.builder.load(element_pointer, name="indexed_current_value")
            operator = node.operator[0]
            if elem_ty == "int":
                operations = {
                    "+": self.builder.add,
                    "-": self.builder.sub,
                    "*": self.builder.mul,
                    "/": self.builder.sdiv,
                }
            elif elem_ty == "float":
                operations = {
                    "+": self.builder.fadd,
                    "-": self.builder.fsub,
                    "*": self.builder.fmul,
                    "/": self.builder.fdiv,
                }
            else:
                raise TypeError(
                    f"Compound indexed assignment is not supported for {elem_ty}"
                )
            value = operations[operator](current_value, value, name="indexed_assignment")
        if val_ty != elem_ty:
            raise TypeError(
                f"Indexed assignment expects {elem_ty}, got {val_ty}"
            )
        self.builder.store(value, element_pointer)

    def visit_DictionaryAccessNode(self, node):
        if not isinstance(node.dictionary, VariableAccessNode):
            raise TypeError("Field access requires a variable")
        var_name = node.dictionary.variable_name
        variable_type = self.type_information.get(var_name)
        if variable_type == "dictionary":
            field_information = self.dictionary_information[var_name].get(node.key)
            if field_information is None:
                raise NameError(f"Dictionary has no field '{node.key}'")
            field_index, field_ty = field_information
            aggregate_pointer = self.variable_pointers[var_name]
        elif variable_type and variable_type.startswith("class:"):
            cls_name = variable_type.removeprefix("class:")
            class_definition = self.class_definitions[cls_name]
            field_information = class_definition["fields"].get(node.key)
            if field_information is None:
                raise NameError(f"Class '{cls_name}' has no field '{node.key}'")
            field_index, field_ty, _ = field_information
            aggregate_pointer = self.variable_pointers[var_name]
        else:
            raise TypeError(f"'{var_name}' does not have readable fields")

        field_pointer = self.builder.gep(
            aggregate_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
            name=f"{var_name}_{node.key}_pointer",
        )
        return self.builder.load(field_pointer, name=f"{var_name}_{node.key}"), field_ty

    def visit_MethodCallNode(self, node):
        if not isinstance(node.receiver, VariableAccessNode):
            raise TypeError("Class method calls need an instance variable as the receiver")

        receiver_name = node.receiver.variable_name
        receiver_type = self.type_information.get(receiver_name)
        if not receiver_type or not receiver_type.startswith("class:"):
            raise TypeError(f"'{receiver_name}' is not a class instance")

        cls_name = receiver_type.removeprefix("class:")
        class_definition = self.class_definitions[cls_name]
        nested_class_name = class_definition["nested_classes"].get(node.method_name)
        if nested_class_name is not None:
            return self.create_class_instance(nested_class_name, node.arguments)

        method_information = self.class_methods.get((cls_name, node.method_name))
        if method_information is None:
            raise NameError(f"Class '{cls_name}' has no method or nested class '{node.method_name}'")

        params = method_information["parameters"]
        if len(node.arguments) != len(params):
            raise TypeError(
                f"Method '{cls_name}.{node.method_name}' expects {len(params)} "
                f"arguments, got {len(node.arguments)}"
            )

        argument_values = [self.variable_pointers[receiver_name]]
        for arg, (parameter_name, parameter_type) in zip(node.arguments, params):
            value, val_ty = self.visit(arg)
            if val_ty != parameter_type:
                raise TypeError(
                    f"Method argument '{parameter_name}' expects {parameter_type}, got {val_ty}"
                )
            argument_values.append(value)

        res = self.builder.call(
            method_information["function"],
            argument_values,
            name=f"{receiver_name}_{node.method_name}_result",
        )
        return res, method_information["return_type"]

    def visit_ForLoopNode(self, node):
        if isinstance(node.iterable, DictionaryAccessNode) and node.iterable.key == "values":
            if not isinstance(node.iterable.dictionary, VariableAccessNode):
                raise TypeError("Dictionary value loops require a dictionary variable")
            dictionary_name = node.iterable.dictionary.variable_name
            fields = self.dictionary_information.get(dictionary_name)
            if fields is None:
                raise TypeError(f"'{dictionary_name}' is not a dictionary")
            self.emit_dictionary_value_loop(dictionary_name, node.item_name, node.body)
            return

        if isinstance(node.iterable, VariableAccessNode):
            collection_name = node.iterable.variable_name
            collection_type = self.type_information.get(collection_name)
            if collection_type == "array":
                array_info = self.array_information[collection_name]
                self.emit_array_loop(
                    self.variable_pointers[collection_name],
                    array_info["element_type"],
                    array_info["length"],
                    node.item_name,
                    node.body,
                )
                return
            if collection_type == "dictionary":
                field_names = list(self.dictionary_information[collection_name])
                self.emit_dictionary_key_loop(field_names, node.item_name, node.body)
                return

        iterable_value, iterable_type = self.visit(node.iterable)
        if isinstance(iterable_value, ArrayLiteralValue):
            array_pointer = self.materialize_array(iterable_value, f"{node.item_name}_array")
            self.emit_array_loop(
                array_pointer,
                iterable_value.element_type,
                len(iterable_value.elements),
                node.item_name,
                node.body,
            )
            return
        if isinstance(iterable_value, DictionaryLiteralValue):
            field_names = [field_name for field_name, _, _ in iterable_value.entries]
            self.emit_dictionary_key_loop(field_names, node.item_name, node.body)
            return
        raise TypeError(f"For loops cannot iterate over values of type '{iterable_type}'")

    def visit_WhileLoopNode(self, node):
        fn = self.builder.function
        condition_block = fn.append_basic_block(name="while_condition")
        body_block = fn.append_basic_block(name="while_body")
        end_block = fn.append_basic_block(name="while_end")
        self.builder.branch(condition_block)

        self.builder.position_at_end(condition_block)
        condition_value, condition_type = self.visit(node.condition)
        if condition_type != "bool":
            raise TypeError(f"while condition must be bool, got {condition_type}")
        self.builder.cbranch(condition_value, body_block, end_block)

        self.builder.position_at_end(body_block)
        visible_variable_pointers = self.variable_pointers.copy()
        visible_type_information = self.type_information.copy()
        visible_array_information = self.array_information.copy()
        visible_dictionary_information = self.dictionary_information.copy()
        visible_constant_variables = self.constant_variables.copy()
        for stmt in node.body:
            self.visit(stmt)
        if not self.builder.block.is_terminated:
            self.builder.branch(condition_block)

        self.variable_pointers = visible_variable_pointers
        self.type_information = visible_type_information
        self.array_information = visible_array_information
        self.dictionary_information = visible_dictionary_information
        self.constant_variables = visible_constant_variables
        self.builder.position_at_end(end_block)

    def emit_dictionary_value_loop(self, dictionary_name, item_name, body):
        dictionary_pointer = self.variable_pointers[dictionary_name]
        saved_variable_pointers = self.variable_pointers.copy()
        saved_type_information = self.type_information.copy()
        saved_array_information = self.array_information.copy()
        saved_dictionary_information = self.dictionary_information.copy()
        saved_constant_variables = self.constant_variables.copy()

        for field_name, (field_index, field_ty) in self.dictionary_information[dictionary_name].items():
            field_pointer = self.builder.gep(
                dictionary_pointer,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
                name=f"{dictionary_name}_{field_name}_value_pointer",
            )
            self.variable_pointers[item_name] = field_pointer
            self.type_information[item_name] = field_ty
            self.array_information.pop(item_name, None)
            self.dictionary_information.pop(item_name, None)

            for stmt in body:
                self.visit(stmt)
            if self.builder.block.is_terminated:
                break

            self.variable_pointers = saved_variable_pointers.copy()
            self.type_information = saved_type_information.copy()
            self.array_information = saved_array_information.copy()
            self.dictionary_information = saved_dictionary_information.copy()
            self.constant_variables = saved_constant_variables.copy()

        self.variable_pointers = saved_variable_pointers
        self.type_information = saved_type_information
        self.array_information = saved_array_information
        self.dictionary_information = saved_dictionary_information
        self.constant_variables = saved_constant_variables

    def materialize_array(self, array_value, array_name):
        array_type = ir.ArrayType(self.llvm_type_for(array_value.element_type), len(array_value.elements))
        array_pointer = self.builder.alloca(array_type, name=array_name)
        for idx, elem in enumerate(array_value.elements):
            element_pointer = self.builder.gep(
                array_pointer,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)],
            )
            self.builder.store(elem, element_pointer)
        return array_pointer

    def emit_dictionary_key_loop(self, field_names, item_name, body):
        key_values = [self.visit_LiteralNode(LiteralNode("str", field_name))[0] for field_name in field_names]
        key_array = ArrayLiteralValue(key_values, "str")
        key_pointer = self.materialize_array(key_array, f"{item_name}_keys")
        self.emit_array_loop(key_pointer, "str", len(field_names), item_name, body)

    def emit_array_loop(self, array_pointer, element_type, array_length, item_name, body):

        fn = self.builder.function
        preheader_block = self.builder.block
        condition_block = fn.append_basic_block(name="for_condition")
        body_block = fn.append_basic_block(name="for_body")
        end_block = fn.append_basic_block(name="for_end")
        self.builder.branch(condition_block)

        self.builder.position_at_end(condition_block)
        item_index = self.builder.phi(self.int32_type, name="for_index")
        item_index.add_incoming(ir.Constant(self.int32_type, 0), preheader_block)
        has_next_item = self.builder.icmp_signed(
            "<", item_index, ir.Constant(self.int32_type, array_length), name="for_has_item"
        )
        self.builder.cbranch(has_next_item, body_block, end_block)

        self.builder.position_at_end(body_block)
        item_pointer = self.builder.gep(
            array_pointer,
            [ir.Constant(self.int32_type, 0), item_index],
            name=f"{item_name}_pointer",
        )
        saved_variable_pointers = self.variable_pointers.copy()
        saved_type_information = self.type_information.copy()
        saved_array_information = self.array_information.copy()
        saved_dictionary_information = self.dictionary_information.copy()
        saved_constant_variables = self.constant_variables.copy()
        self.variable_pointers[item_name] = item_pointer
        self.type_information[item_name] = element_type
        self.array_information.pop(item_name, None)
        self.dictionary_information.pop(item_name, None)

        for stmt in body:
            self.visit(stmt)

        if not self.builder.block.is_terminated:
            loop_end_block = self.builder.block
            next_item_index = self.builder.add(item_index, ir.Constant(self.int32_type, 1), name="for_next_index")
            self.builder.branch(condition_block)
            item_index.add_incoming(next_item_index, loop_end_block)

        self.variable_pointers = saved_variable_pointers
        self.type_information = saved_type_information
        self.array_information = saved_array_information
        self.dictionary_information = saved_dictionary_information
        self.constant_variables = saved_constant_variables
        self.builder.position_at_end(end_block)

    def visit_BinaryOpNode(self, node):
        lhs, lhs_ty = self.visit(node.left)
        rhs, rhs_ty = self.visit(node.right)

        if lhs_ty == "str" or rhs_ty == "str":
            if lhs_ty != "str":
                lhs, _ = self.visit_CastNode(type("Cast", (), {"expression": node.left, "target_type": "str"})())
            if rhs_ty != "str":
                rhs, _ = self.visit_CastNode(type("Cast", (), {"expression": node.right, "target_type": "str"})())

            left_length = self.builder.call(self.strlen_function, [lhs])
            right_length = self.builder.call(self.strlen_function, [rhs])
            buffer_length = self.builder.add(self.builder.add(left_length, right_length), ir.Constant(self.int32_type, 1))

            buf = self.allocate_bytes(buffer_length, name="string_concat_buffer")
            self.builder.call(self.strcpy_function, [buf, lhs])
            self.builder.call(self.strcat_function, [buf, rhs])
            return buf, "str"

        if lhs_ty != rhs_ty:
            raise TypeError(f"Type mismatch: {lhs_ty} {node.operator} {rhs_ty}")

        if lhs_ty == "int":
            if node.operator == "+": return self.builder.add(lhs, rhs, name="addtmp"), "int"
            elif node.operator == "-": return self.builder.sub(lhs, rhs, name="subtmp"), "int"
            elif node.operator == "*": return self.builder.mul(lhs, rhs, name="multmp"), "int"
            elif node.operator == "/": return self.builder.sdiv(lhs, rhs, name="divtmp"), "int"
        elif lhs_ty == "float":
            if node.operator == "+": return self.builder.fadd(lhs, rhs, name="faddtmp"), "float"
            elif node.operator == "-": return self.builder.fsub(lhs, rhs, name="fsubtmp"), "float"
            elif node.operator == "*": return self.builder.fmul(lhs, rhs, name="fmultmp"), "float"
            elif node.operator == "/": return self.builder.fdiv(lhs, rhs, name="fdivtmp"), "float"

        raise SyntaxError(f"Unsupported binary operator '{node.operator}' for type '{lhs_ty}'")

    def visit_ComparisonNode(self, node):
        lhs, lhs_ty = self.visit(node.left)
        rhs, rhs_ty = self.visit(node.right)

        if lhs_ty != rhs_ty:
            raise TypeError(f"Cannot compare {lhs_ty} with {rhs_ty}")

        if lhs_ty == "float":
            if node.operator == "!=":
                return self.builder.fcmp_unordered(node.operator, lhs, rhs), "bool"
            return self.builder.fcmp_ordered(node.operator, lhs, rhs), "bool"

        if lhs_ty == "str":
            comparison = self.builder.call(self.strcmp_function, [lhs, rhs])
            return self.builder.icmp_signed(node.operator, comparison, ir.Constant(self.int32_type, 0)), "bool"

        if lhs_ty == "bool" and node.operator not in ("==", "!="):
            raise SyntaxError("Boolean values only support == and != comparisons")
        if lhs_ty in ("int", "bool"):
            return self.builder.icmp_signed(node.operator, lhs, rhs), "bool"

        raise SyntaxError(f"Values of type '{lhs_ty}' cannot be compared")

    def visit_IfNode(self, node):
        fn = self.builder.function
        merge_block = fn.append_basic_block(name="if_end")
        visible_variable_pointers = self.variable_pointers.copy()
        visible_type_information = self.type_information.copy()
        visible_array_information = self.array_information.copy()
        visible_dictionary_information = self.dictionary_information.copy()
        visible_constant_variables = self.constant_variables.copy()

        for cond, body in node.branches:
            condition_value, condition_type = self.visit(cond)
            if condition_type != "bool":
                raise TypeError(f"if condition must be bool, got {condition_type}")

            body_block = fn.append_basic_block(name="if_body")
            next_branch_block = fn.append_basic_block(name="if_next")
            self.builder.cbranch(condition_value, body_block, next_branch_block)

            self.builder.position_at_end(body_block)
            for stmt in body:
                self.visit(stmt)
            if not self.builder.block.is_terminated:
                self.builder.branch(merge_block)

            self.variable_pointers = visible_variable_pointers.copy()
            self.type_information = visible_type_information.copy()
            self.array_information = visible_array_information.copy()
            self.dictionary_information = visible_dictionary_information.copy()
            self.constant_variables = visible_constant_variables.copy()
            self.builder.position_at_end(next_branch_block)

        if node.else_body is not None:
            for stmt in node.else_body:
                self.visit(stmt)
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_block)

        self.variable_pointers = visible_variable_pointers
        self.type_information = visible_type_information
        self.array_information = visible_array_information
        self.dictionary_information = visible_dictionary_information
        self.constant_variables = visible_constant_variables
        self.builder.position_at_end(merge_block)

    def visit_CastNode(self, node):
        value, val_ty = self.visit(node.expression)
        tgt_ty = node.target_type

        if val_ty == tgt_ty:
            return value, tgt_ty

        if tgt_ty == "int":
            if val_ty == "float":
                return self.builder.fptosi(value, self.int32_type, name="cast_int"), "int"
            elif val_ty == "bool":
                return self.builder.zext(value, self.int32_type, name="cast_int"), "int"
            elif val_ty == "str":
                return self.builder.call(self.atoi_function, [value], name="atoi_tmp"), "int"

        elif tgt_ty == "float":
            if val_ty == "int":
                return self.builder.sitofp(value, self.float_type, name="cast_float"), "float"
            elif val_ty == "bool":
                integer_value = self.builder.zext(value, self.int32_type, name="bool_int")
                return self.builder.sitofp(integer_value, self.float_type, name="cast_float"), "float"
            elif val_ty == "str":
                double_value = self.builder.call(self.atof_function, [value], name="atof_tmp")
                return self.builder.fptrunc(double_value, self.float_type, name="fptrunc_tmp"), "float"

        elif tgt_ty == "bool":
            if val_ty == "int":
                return self.builder.icmp_signed("!=", value, ir.Constant(self.int32_type, 0), name="cast_bool"), "bool"
            elif val_ty == "float":
                return self.builder.fcmp_ordered("!=", value, ir.Constant(self.float_type, 0.0), name="cast_bool"), "bool"
            elif val_ty == "str":
                true_string = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
                one_string = self.visit_LiteralNode(LiteralNode("str", "1"))[0]
                true_comparison = self.builder.call(self.strcmp_function, [value, true_string])
                one_comparison = self.builder.call(self.strcmp_function, [value, one_string])
                is_true = self.builder.icmp_signed("==", true_comparison, ir.Constant(self.int32_type, 0))
                is_one = self.builder.icmp_signed("==", one_comparison, ir.Constant(self.int32_type, 0))
                return self.builder.or_(is_true, is_one, name="cast_bool"), "bool"

        elif tgt_ty == "str":
            buf = self.allocate_bytes(
                ir.Constant(self.int32_type, 64),
                name="string_buffer",
            )
            buffer_size = ir.Constant(self.int32_type, 64)
            if val_ty == "int":
                format_string = self.visit_LiteralNode(LiteralNode("str", "%d"))[0]
                self.builder.call(self.snprintf_function, [buf, buffer_size, format_string, value])
                return buf, "str"
            elif val_ty == "float":
                format_string = self.visit_LiteralNode(LiteralNode("str", "%f"))[0]
                double_value = self.builder.fpext(value, ir.DoubleType())
                self.builder.call(self.snprintf_function, [buf, buffer_size, format_string, double_value])
                return buf, "str"
            elif val_ty == "bool":
                true_string = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
                false_string = self.visit_LiteralNode(LiteralNode("str", "false"))[0]
                return self.builder.select(value, true_string, false_string), "str"

        raise TypeError(f"Casting from {val_ty} to {tgt_ty} is not supported.")

    def visit_VariableDeclarationNode(self, node):
        value, val_ty = self.visit(node.initializer)
        if node.variable_type is not None and val_ty != node.variable_type:
            raise TypeError(f"Cannot assign {val_ty} to variable '{node.variable_name}' of type {node.variable_type}")

        if node.is_constant:
            self.constant_variables.add(node.variable_name)
        else:
            self.constant_variables.discard(node.variable_name)

        if isinstance(value, ClassInstanceValue):
            self.variable_pointers[node.variable_name] = value.pointer
            self.type_information[node.variable_name] = val_ty
            self.array_information.pop(node.variable_name, None)
            self.dictionary_information.pop(node.variable_name, None)
            return

        if isinstance(value, ArrayLiteralValue):
            array_type = ir.ArrayType(self.llvm_type_for(value.element_type), len(value.elements))
            variable_pointer = self.builder.alloca(array_type, name=node.variable_name)
            for idx, elem in enumerate(value.elements):
                element_pointer = self.builder.gep(
                    variable_pointer,
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)],
                )
                self.builder.store(elem, element_pointer)
            self.variable_pointers[node.variable_name] = variable_pointer
            self.type_information[node.variable_name] = "array"
            self.array_information[node.variable_name] = {
                "element_type": value.element_type,
                "length": len(value.elements),
            }
            self.dictionary_information.pop(node.variable_name, None)
            return

        if isinstance(value, DictionaryLiteralValue):
            dictionary_type = ir.LiteralStructType([
                self.llvm_type_for(field_ty)
                for _, field_ty, _ in value.entries
            ])
            variable_pointer = self.builder.alloca(dictionary_type, name=node.variable_name)
            fields = {}
            for field_index, (field_name, field_ty, field_value) in enumerate(value.entries):
                field_pointer = self.builder.gep(
                    variable_pointer,
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
                )
                self.builder.store(field_value, field_pointer)
                fields[field_name] = (field_index, field_ty)
            self.variable_pointers[node.variable_name] = variable_pointer
            self.type_information[node.variable_name] = "dictionary"
            self.dictionary_information[node.variable_name] = fields
            self.array_information.pop(node.variable_name, None)
            return

        variable_type = node.variable_type or val_ty
        if isinstance(value, PointerValue):
            value = value.pointer
        variable_pointer = self.builder.alloca(self.llvm_type_for(variable_type), name=node.variable_name)
        self.builder.store(value, variable_pointer)
        self.variable_pointers[node.variable_name] = variable_pointer
        self.type_information[node.variable_name] = variable_type
        self.array_information.pop(node.variable_name, None)
        self.dictionary_information.pop(node.variable_name, None)

    def visit_GroupVariableDeclarationNode(self, node):
        if node.variable_type is None:
            raise SyntaxError("Grouped declarations require an explicit type")
        if len(set(node.variable_names)) != len(node.variable_names):
            raise SyntaxError("Grouped declarations cannot contain duplicate variable names")
        if node.initializers is not None and len(node.initializers) != len(node.variable_names):
            raise SyntaxError(
                f"Grouped declaration has {len(node.variable_names)} variables but "
                f"{len(node.initializers)} initializers"
            )

        if node.initializers is None:
            defaults = {
                "int": LiteralNode("int", 0),
                "float": LiteralNode("float", 0.0),
                "bool": LiteralNode("bool", False),
                "str": LiteralNode("str", ""),
            }
            initializer = defaults.get(node.variable_type)
            if initializer is None:
                raise TypeError(
                    f"Grouped declarations do not support default initialization "
                    f"for {node.variable_type}"
                )
            initializers = [initializer] * len(node.variable_names)
        else:
            initializers = node.initializers

        for var_name, initializer in zip(node.variable_names, initializers):
            self.visit(
                VariableDeclarationNode(
                    node.is_constant,
                    var_name,
                    node.variable_type,
                    initializer,
                )
            )

    def visit_PrintNode(self, node):
        value, val_ty = self.visit(node.expression)
        end = "\n\0" if node.newline else "\0"
        format_string = f"%s{end}" if val_ty == "str" else f"%d{end}" if val_ty == "int" else f"%f{end}" if val_ty == "float" else f"%s{end}"

        format_constant = ir.Constant(ir.ArrayType(ir.IntType(8), len(format_string)), bytearray(format_string.encode("utf-8")))
        self.string_literal_count += 1
        format_global = ir.GlobalVariable(self.module, format_constant.type, name=f".str_{self.string_literal_count}")
        format_global.linkage = "internal"
        format_global.initializer = format_constant
        format_pointer = self.builder.bitcast(format_global, self.char_pointer_type)

        if val_ty == "float":
            value = self.builder.fpext(value, ir.DoubleType())
        elif val_ty == "bool":
            true_string = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
            false_string = self.visit_LiteralNode(LiteralNode("str", "false"))[0]
            value = self.builder.select(value, true_string, false_string)

        self.builder.call(self.printf_function, [format_pointer, value])

    def visit_ExitNode(self, node):
        exit_code, exit_code_type = self.visit(node.exit_code)
        if exit_code_type != "int":
            raise TypeError(f"exit() expected int exit code, got {exit_code_type}")
        self.builder.call(self.exit_function, [exit_code])

    def visit_FreeNode(self, node):
        ptr, pointer_type = self.visit(node.pointer_expression)
        if pointer_type != "str" and not pointer_type.startswith("pointer:"):
            raise TypeError(f"free() expected an allocated pointer, got {pointer_type}")
        if isinstance(ptr, PointerValue):
            ptr = ptr.pointer
        if ptr.type != self.char_pointer_type:
            ptr = self.builder.bitcast(ptr, self.char_pointer_type, name="free_pointer")
        self.builder.call(self.free_function, [ptr])
        
    def llvm_type_for(self, type_name):
        if type_name == "int": return self.int32_type
        elif type_name == "float": return self.float_type
        elif type_name == "bool": return self.bool_type
        elif type_name == "str": return self.char_pointer_type
        elif type_name.startswith("pointer:"):
            return self.llvm_type_for(type_name.removeprefix("pointer:")).as_pointer()
        elif type_name == "void": return ir.VoidType()
        elif type_name.startswith("class:"):
            cls_name = type_name.removeprefix("class:")
            return self.class_definitions[cls_name]["llvm_type"]
        return self.int32_type

    def visit_FunctionDeclarationNode(self, node):
        previous_builder = self.builder
        previous_variable_pointers = self.variable_pointers.copy()
        previous_type_information = self.type_information.copy()
        previous_array_information = self.array_information.copy()
        previous_dictionary_information = self.dictionary_information.copy()
        previous_constant_variables = self.constant_variables.copy()

        parameter_types = [self.llvm_type_for(parameter_type) for _, parameter_type in node.parameters]
        return_llvm_type = self.llvm_type_for(node.return_type)

        function_type = ir.FunctionType(return_llvm_type, parameter_types)
        fn = ir.Function(self.module, function_type, name=node.function_name)
        fn.attributes.add("noinline")
        
        self.type_information[f"function_{node.function_name}"] = node.return_type

        entry_block = fn.append_basic_block(name="entry")
        self.builder = ir.IRBuilder(entry_block)

        for idx, (parameter_name, parameter_type) in enumerate(node.parameters):
            parameter_llvm_type = self.llvm_type_for(parameter_type)
            parameter_pointer = self.builder.alloca(parameter_llvm_type, name=parameter_name)
            self.builder.store(fn.args[idx], parameter_pointer)
            self.variable_pointers[parameter_name] = parameter_pointer
            self.type_information[parameter_name] = parameter_type

        for stmt in node.body:
            self.visit(stmt)

        if not self.builder.block.is_terminated:
            if isinstance(return_llvm_type, ir.VoidType):
                raise SyntaxError(
                    f"Function '{node.function_name}' must end with 'return : void'"
                )
            raise SyntaxError(f"Function '{node.function_name}' must return a value")

        self.builder = previous_builder
        self.variable_pointers = previous_variable_pointers
        self.type_information = previous_type_information
        self.array_information = previous_array_information
        self.dictionary_information = previous_dictionary_information
        self.constant_variables = previous_constant_variables
        self.type_information[f"function_{node.function_name}"] = node.return_type

    def visit_ReturnNode(self, node):
        function_return_type = self.builder.function.function_type.return_type
        if node.return_type == "void" or node.expression is None:
            if not isinstance(function_return_type, ir.VoidType):
                raise TypeError("A void return can only be used in a void function or method")
            self.builder.ret_void()
            return None, "void"

        value, val_ty = self.visit(node.expression)
        if node.return_type is not None and val_ty != node.return_type:
            raise TypeError(f"Return annotation expects {node.return_type}, got {val_ty}")
        if value.type != function_return_type:
            raise TypeError(f"Return value of type {val_ty} does not match the function return type")
        self.builder.ret(value)

    def visit_FunctionCallNode(self, node):
        if node.function_name in self.class_definitions:
            return self.create_class_instance(node.function_name, node.arguments)

        fn = self.module.get_global(node.function_name)
        argument_values = []
        for arg in node.arguments:
            value, _ = self.visit(arg)
            argument_values.append(value)

        ret_ty = self.type_information.get(f"function_{node.function_name}", "int")
        res = self.builder.call(fn, argument_values, name=f"{node.function_name}_result")
        return res, ret_ty

    def create_class_instance(self, class_name, arguments, instance_name=None):
        class_definition = self.class_definitions.get(class_name)
        if class_definition is None:
            raise NameError(f"Class '{class_name}' is not declared")

        field_order = class_definition["field_order"]
        if len(arguments) != len(field_order):
            raise TypeError(
                f"Class '{class_name}' expects {len(field_order)} values, got {len(arguments)}"
            )

        instance_pointer = self.builder.alloca(
            class_definition["llvm_type"],
            name=instance_name or f"{class_name.lower()}_instance",
        )
        for field_index, (field_name, arg) in enumerate(zip(field_order, arguments)):
            value, val_ty = self.visit(arg)
            _, want_ty, _ = class_definition["fields"][field_name]
            if val_ty != want_ty:
                raise TypeError(
                    f"Field '{field_name}' in class '{class_name}' expects "
                    f"{want_ty}, got {val_ty}"
                )
            field_pointer = self.builder.gep(
                instance_pointer,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
                name=f"{field_name}_pointer",
            )
            self.builder.store(value, field_pointer)

        return ClassInstanceValue(instance_pointer), f"class:{class_name}"