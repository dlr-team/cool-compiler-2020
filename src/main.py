#!/usr/bin/python3

from engine import *
import sys

args = sys.argv

# if len(args) != 3:
#     exit(1)

input_file = open(args[1], "r")
output_file = open(args[2], 'w')

# input_file = open('./src/test.cl', "r")
# output_file = open('./src/test.mips', 'w')

t = input_file.read()

# output_file = args[2]

lexer = CoolLexer()
tokens, errors = lexer.tokenize(t)

if len(errors):
    for e in errors:
        print(e)
    exit(1)

if not tokens:
    print(SyntacticError(0, 0, 'ERROR at or near "%s"' % 'EOF'))
    exit(1)

lexer = CoolLexer()
parser = CoolParser(lexer)
ast, errors = parser.parse(t)

if errors:
    for error in errors:
        print(error)
    exit(1)
# print(ast)

# fmatter = Format()
# tree = fmatter.visit(ast, 0)

# print(tree)

collect_errors = []
collect = Collector(collect_errors)
collect.visit(ast)

if len(collect_errors):
    # print("coolector")
    for e in collect_errors[::-1]:
        print(e)
    exit(1)

context = collect.context
builder_errors = []
builder = Builder(context, builder_errors)
builder.visit(ast)

if len(builder_errors):
    # print("builder")
    for e in builder_errors[::-1]:
        print(e)
    exit(1)

context = builder.context
checker_errors = []
checker = Checker(context, checker_errors)
scope = checker.visit(ast)

if len(checker_errors):
    # print("checker")
    for e in checker_errors[::-1]:
        print(e)
    exit(1)


cil = COOL_TO_CIL(checker.context)
# cil = COOL_TO_CIL_VISITOR(checker.context)
# sc = Scope()
cil_ast = cil.visit(ast)
# f_ast = Format().visit(ast)
emsamb = CIL_TO_MIPS()
emsamb.visit(cil_ast)
m_ast = emsamb.mips.compile()
# f_ast = CIL_FORMATTER().visit(cil_ast)
string_formatted = str(m_ast)
output_file.write(string_formatted)
# output_file.write(str(collect_errors))
# print(str(collect_errors))
# output_file.write(str(builder_errors))
# output_file.write(str(checker_errors))
# output_file.write(collect_errors)
input_file.close()
output_file.close()


# if not operations:
#     message = f'ERROR at or near "{parse.lex}"'
#     print(SyntacticError(parse.line, parse.column, message))
#     exit(1)
# print(parse)


exit(0)
