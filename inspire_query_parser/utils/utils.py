# coding=utf-8
from ..ast import UnaryOp, Leaf, BinaryOp, ListOp

INDENTATION = 4


def emit_symbol_at_level_str(symbol, level, is_last=False):
    def emit_prefix():
        ret_str = ""
        prefix = ("└── " if is_last else "├── ") if level != 0 else ""
        for i in range(level):
            if i % INDENTATION == 0:
                ret_str += "│"
            else:
                ret_str += " "
        return ret_str + prefix
    return emit_prefix() + str(symbol) + "\n"


def recursive_printer(node, level=-INDENTATION):
    new_level = INDENTATION + level

    if issubclass(type(node), Leaf):
        value = "" if not node.value.__str__() or node.value.__str__() == "None" \
            else node.__class__.__name__ + " {" + node.value.__str__() + "}"

        ret_str = emit_symbol_at_level_str(value, new_level) if value != "" else ""
    else:
        ret_str = emit_symbol_at_level_str(node.__class__.__name__, new_level)
        if issubclass(type(node), UnaryOp):
            ret_str += recursive_printer(node.op, new_level)
            if not node.op:
                ret_str = ""

        elif issubclass(type(node), BinaryOp):
            ret_str += recursive_printer(node.left, new_level)
            ret_str += recursive_printer(node.right, new_level)

        elif issubclass(type(node), ListOp):
            for c in node.children:
                ret_str += recursive_printer(c, new_level)
            ret_str += emit_symbol_at_level_str("▆", new_level, True)

        elif not node:
            return ""
        else:
            raise TypeError("Unexpected base type: " + str(type(node)))

    return ret_str


def tree_print(tree):
    ret_str = recursive_printer(tree)
    ret_str += emit_symbol_at_level_str("▆", 0, True)
    return ret_str


if __name__ == '__main__':
    pass
    # from pypeg2 import parse
    # tree = parse("author ellis, j and title foo", StartRule)
    # print(tree)
    # print("\n" + tree_print(tree))
