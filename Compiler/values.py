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
    def __init__(self, pointer, temporary=False):
        self.pointer = pointer
        self.temporary = temporary


class PointerValue:
    def __init__(self, pointer, element_type):
        self.pointer = pointer
        self.element_type = element_type
