from engine import parser as cool
from .cil_ast import *
from ..cp import visitor
from ..cp.semantic import VariableInfo, Scope
from .cil import BASE_COOL_CIL_TRANSFORM


class COOL_TO_CIL(BASE_COOL_CIL_TRANSFORM):

    def define_binary_node(self, node: cool.BinaryNode, scope, cil_node: Node):
        result = self.define_internal_local()
        left = self.visit(node.left, scope)
        right = self.visit(node.right, scope)
        self.register_instruction(cil_node(result, left, right))
        return result

    def define_unary_node(self, node: cool.UnaryNode, scope, cil_node: Node):
        result = self.define_internal_local()
        expr = self.visit(node.expression, scope)
        self.register_instruction(cil_node(result, expr))
        return result

    def init_class_attr(self, scope: Scope, class_id, self_inst):
        attr_nodes = self.attr_init[class_id]
        for attr in attr_nodes:
            attr_scope = Scope(parent=scope)
            attr_scope.define_variable('self', self_inst)
            self.visit(attr, attr_scope)

    def save_attr_init(self, node: cool.ProgramNode):
        self.attr_init = dict()
        classes = [declaration for declaration in node.declarations if isinstance(
            declaration, cool.ClassDeclarationNode)]
        for declaration in classes:
            self.attr_init[declaration.id.lex] = []
            if declaration.parent and not declaration.parent.lex in ['IO', 'Object']:
                self.attr_init[declaration.id.lex] += self.attr_init[declaration.parent.lex]
            for feature in declaration.features:
                if isinstance(feature, cool.AttrDeclarationNode):
                    self.attr_init[declaration.id.lex].append(feature)

    @visitor.on('node')
    def visit(self, node, scope):
        pass

    @visitor.when(cool.ProgramNode)
    def visit(self, node: cool.ProgramNode, scope=None):
        scope = Scope()
        self.save_attr_init(node)
        self.current_function = self.register_function('entry')
        instance = self.define_internal_local()
        result = self.define_internal_local()
        self.current_type = self.context.get_type('Main')
        self.register_instruction(AllocateNode(instance, 'Main'))
        self.init_class_attr(scope, 'Main', instance)
        self.register_instruction(ArgNode(instance))
        name = self.to_function_name('main', 'Main')
        self.register_instruction(StaticCallNode(name, result))
        self.current_function = None

        classes = [declaration for declaration in node.declarations if isinstance(
            declaration, cool.ClassDeclarationNode)]
        for declaration in classes:
            self.visit(declaration, scope)

        return ProgramNode(self.dottypes, self.dotdata, self.dotcode)

    @visitor.when(cool.ClassDeclarationNode)
    def visit(self, node: cool.ClassDeclarationNode, scope):
        self.current_type = self.context.get_type(node.id.lex)
        type_node = self.register_type(node.id.lex)
        type_node.attributes = [(attr.name)
                                for attr in self.current_type.all_attributes()]
        type_node.methods = [(method.name, self.to_function_name(
            method.name, xtype.name)) for method, xtype in self.current_type.all_methods()]

        fun_declarations = (f for f in node.features if isinstance(
            f, cool.FuncDeclarationNode))
        for feature in fun_declarations:
            self.visit(feature, scope)

        self.current_type = None

    @visitor.when(cool.FuncDeclarationNode)
    def visit(self, node: cool.FuncDeclarationNode, scope: Scope):
        fun_scope = Scope(parent=scope)
        self.current_method = self.current_type.get_method(node.id.lex)
        type_name = self.current_type.name

        self.current_function = self.register_function(
            self.to_function_name(node.id.lex, type_name))
        self_local = self.register_param(VariableInfo('self', None))
        fun_scope.define_variable('self', self_local)
        for param_name, param_type in node.params:
            fun_scope.define_variable(param_name.lex, param_type.lex)
            self.register_param(VariableInfo(param_name.lex, param_type.lex))

        body = self.visit(node.body, fun_scope)

        self.register_instruction(ReturnNode(body))
        self.current_method = None

    @visitor.when(cool.AttrDeclarationNode)
    def visit(self, node: cool.AttrDeclarationNode, scope):
        result = self.visit(node.expression, scope) if node.expression else 0
        self_inst = scope.find_variable('self').name
        self.register_instruction(
            SetAttribNode(self_inst, node.id.lex, result, self.current_type.name))

    @visitor.when(cool.BlockNode)
    def visit(self, node: cool.BlockNode, scope):
        result = self.define_internal_local()
        for expr in node.expressions:
            val = self.visit(expr, scope)
        self.register_instruction(AssignNode(result, val))
        return result

    @visitor.when(cool.AssignNode)
    def visit(self, node: cool.AssignNode, scope):
        expr = self.visit(node.expression, scope)
        attr_info = scope.find_variable(node.id.lex)
        if not attr_info:
            selfx = scope.find_variable('self').name
            self.register_instruction(SetAttribNode(
                selfx, node.id.lex, expr, self.current_type.name))
        else:
            attr_info = attr_info.name
            self.register_instruction(AssignNode(attr_info, expr))
        return 0

    @visitor.when(cool.NewNode)
    def visit(self, node: cool.NewNode, scope):
        new_local = self.define_internal_local()
        typex = self.context.get_type(node.type.lex)
        self.register_instruction(AllocateNode(new_local, typex.name))
        self.init_class_attr(scope, node.type.lex, new_local)
        return new_local

    @visitor.when(cool.IfThenElseNode)
    def visit(self, node: cool.IfThenElseNode, scope):
        cond = self.visit(node.condition, scope)
        child_scope = Scope(parent=scope)
        true_label = LabelNode(f'TRUE_{self.label_counter}')
        end_label = LabelNode(f'END_{self.label_counter}')
        result = self.define_internal_local()
        self.register_instruction(IfGotoNode(
            cond, true_label.label))
        self.label_counter += 1
        false_expr = self.visit(node.else_body, child_scope)
        self.register_instruction(AssignNode(result, false_expr))
        self.register_instruction(
            GotoNode(end_label.label))
        self.register_instruction(true_label)

        true_expr = self.visit(node.if_body, child_scope)
        self.register_instruction(AssignNode(result, true_expr))
        self.register_instruction(end_label)
        self.label_counter = 0

        return result

    @visitor.when(cool.WhileLoopNode)
    def visit(self, node: cool.WhileLoopNode, scope):
        while_scope = Scope(parent=scope)
        start_label = LabelNode(f'START_{self.label_counter}')
        continue_label = LabelNode(f'CONTINUE_{self.label_counter}')
        end_label = LabelNode(f'END_{self.label_counter}')

        self.register_instruction(start_label)

        cond = self.visit(node.condition, scope)
        self.register_instruction(IfGotoNode(cond, continue_label.label))
        self.register_instruction(GotoNode(end_label.label))
        self.register_instruction(continue_label)
        self.visit(node.body, while_scope)
        self.label_counter += 1
        self.register_instruction(GotoNode(start_label.label))
        self.register_instruction(end_label)

        self.label_counter = 0
        return 0

    @visitor.when(cool.CaseOfNode)
    def visit(self, node: cool.CaseOfNode, scope: Scope):
        expr = self.visit(node.expression, scope)
        result = self.define_internal_local()
        exp_type = self.define_internal_local()
        end_label = LabelNode('END')
        error_label = LabelNode(f'ERROR_CASE_{node.id}')
        # TODO: Label error logic if is void
        self.register_instruction(TypeOfNode(expr, exp_type))

        case_expressions = self.sort_case_list(node.branches)

        for i, case in enumerate(case_expressions):
            next_branch_label = LabelNode(f'CASE_{case.id}_{i}')
            child_scope = Scope(parent=scope)
            expr_i = self.visit(
                case, child_scope,
                expr=expr,
                expr_type=exp_type,
                next_label=next_branch_label,
            )
            self.register_instruction(AssignNode(result, expr_i))
            self.register_instruction(GotoNode(end_label.label))
            self.register_instruction(next_branch_label)

        self.register_instruction(error_label)
        # TODO: specify the message error here [ i think :/ ]
        self.register_instruction(ErrorNode())
        self.register_instruction(end_label)

        return result

    @visitor.when(cool.CaseActionExpression)
    def visit(self, node: cool.CaseActionExpression, scope: Scope, expr=None, expr_type=None, next_label=None):
        test_res = self.define_internal_local()

        matching_label = LabelNode('CASE_MATCH_{node.id}_{node.typex}')
        self.register_instruction(ConformsNode(test_res, expr, node.typex))
        self.register_instruction(IfGotoNode(expr, matching_label))
        self.register_instruction(
            GotoNode(next_label.label)
        )
        self.register_instruction(matching_label)
        l_var = self.define_internal_local()
        typex = self.context.get_type(node.type)
        scope.define_variable(l_var, typex)
        self.register_instruction(AssignNode(l_var, expr))

        case_action_expr = self.visit(node.expression, scope)
        return case_action_expr

    @visitor.when(cool.LetInNode)
    def visit(self, node: cool.LetInNode, scope: Scope):
        let_scope = Scope(parent=scope)
        for var_decl in node.let_body:
            let_scope.define_variable(var_decl.id, var_decl.type)
            self.visit(var_decl, let_scope)

        result = self.visit(node.in_body, let_scope)
        return result

    @visitor.when(cool.LetVariableDeclaration)
    def visit(self, node: cool.LetVariableDeclaration, scope: Scope):
        var_info = scope.find_variable(node.id)
        local_var = self.register_local(var_info.name)

        value = self.visit(node.expression, scope)

        self.register_instruction(AssignNode(local_var, value))
        return local_var

    @visitor.when(cool.FunctionCallNode)
    def visit(self, node: cool.FunctionCallNode, scope):
        if not (node.type):
            typex = self.context.get_type(node.obj.static_type.name).name
        else:
            typex = node.type.lex
        name = self.to_function_name(node.id.lex, typex)
        result = self.define_internal_local()
        rev_args = []
        for arg in node.args:
            arg_value = self.visit(arg, scope)
            rev_args = [arg_value] + rev_args
        for arg_value in rev_args:
            self.register_instruction(ArgNode(arg_value))
        obj = self.visit(node.obj, scope)
        self.register_instruction(ArgNode(obj))
        if name:
            self.register_instruction(StaticCallNode(name, result))
        else:
            self.register_instruction(
                DynamicCallNode(typex, node.id.lex, result))

        return result

    @visitor.when(cool.MemberCallNode)
    def visit(self, node: cool.MemberCallNode, scope: Scope):
        type_name = self.current_type.name
        result = self.define_internal_local()
        rev_args = []
        for arg in node.args:
            arg_value = self.visit(arg, scope)
            rev_args = [arg_value] + rev_args
        for arg_value in rev_args:
            self.register_instruction(ArgNode(arg_value))
        self_inst = scope.find_variable('self').name
        self.register_instruction(ArgNode(self_inst))
        self.register_instruction(
            DynamicCallNode(type_name, node.id.lex, result))

        return result

    @visitor.when(cool.PlusNode)
    def visit(self, node: cool.PlusNode, scope):
        return self.define_binary_node(node, scope, PlusNode)

    @visitor.when(cool.MinusNode)
    def visit(self, node: cool.MinusNode, scope):
        return self.define_binary_node(node, scope, MinusNode)

    @visitor.when(cool.StarNode)
    def visit(self, node: cool.StarNode, scope):
        return self.define_binary_node(node, scope, StarNode)

    @visitor.when(cool.DivNode)
    def visit(self, node: cool.DivNode, scope):
        return self.define_binary_node(node, scope, DivNode)

    @visitor.when(cool.LessNode)
    def visit(self, node: cool.LessNode, scope):
        return self.define_binary_node(node, scope, LessNode)

    @visitor.when(cool.LessEqualNode)
    def visit(self, node: cool.LessEqualNode, scope):
        return self.define_binary_node(node, scope, LessEqNode)

    @visitor.when(cool.EqualNode)
    def visit(self, node: cool.EqualNode, scope):
        left = self.visit(node.left, scope)
        right = self.visit(node.right, scope)
        result = self.define_internal_local()

        if node.left.static_type == self.context.get_type('String'):
            self.register_instruction(StringEqualNode(result, left, right))
        else:
            self.register_instruction(EqualNode(result, left, right))
        return result

    @visitor.when(cool.IsVoidNode)
    def visit(self, node: cool.IsVoidNode, scope):
        return self.define_unary_node(node, scope, IsVoidNode)

    @visitor.when(cool.NotNode)
    def visit(self, node: cool.NotNode, scope):
        return self.define_unary_node(node, scope, NotNode)

    @visitor.when(cool.ComplementNode)
    def visit(self, node: cool.ComplementNode, scope):
        return self.define_unary_node(node, scope, ComplementNode)

    @visitor.when(cool.IdNode)
    def visit(self, node: cool.IdNode, scope: Scope):
        nvar = scope.find_variable(node.token.lex)
        if not nvar:
            selfx = scope.find_variable('self').name
            nvar = self.define_internal_local()
            self.register_instruction(
                GetAttribNode(nvar, selfx, node.token.lex, self.current_type.name))
        else:
            nvar = nvar.name
        return nvar

    @visitor.when(cool.BoolNode)
    def visit(self, node: cool.BoolNode, scope):
        return 1 if node.token.lex else 0

    @visitor.when(cool.IntegerNode)
    def visit(self, node: cool.IntegerNode, scope):
        return int(node.token.lex)

    @visitor.when(cool.StringNode)
    def visit(self, node: cool.StringNode, scope):
        string = self.register_data(node.token.lex)
        dest = self.define_internal_local()
        self.register_instruction(LoadNode(dest, string.name))
        return dest
