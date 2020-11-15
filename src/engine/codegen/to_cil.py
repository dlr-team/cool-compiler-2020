import parser as cool
from .cil_ast import ProgramNode, TypeNode, FunctionNode, ParamNode, LocalNode, AssignNode, PlusNode \
    , MinusNode, StarNode, DivNode, AllocateNode, TypeOfNode, StaticCallNode, DynamicCallNode    \
    , ArgNode, ReturnNode, ReadNode, PrintNode, LoadNode, LengthNode, ConcatNode, PrefixNode     \
    , SubstringNode, ToStrNode, GetAttribNode, SetAttribNode, LabelNode, GotoNode, IfGotoNode    \
    , DataNode, ToIntNode

from .cil import BASE_COOL_CIL_TRANSFORM, VariableInfo
from .utils import Scope
from ..cp.visitor import when,on



class COOL_TO_CIL_VISITOR(BASE_COOL_CIL_TRANSFORM):
    @on('node')
    def visit(self, node, scope:Scope):
        pass
    
    def order_caseof(self, node:cool.CaseOfNode):
        return list(node.cases)

    def find_type_name(self, typex, func_name):
        if func_name in typex.methods:
            return typex.name
        return self.find_type_name(typex.parent, func_name)

    def init_class_attr(self, scope:Scope, class_id, self_inst):
        attr_nodes = self.attr_init[class_id]
        for attr in attr_nodes:
            attr_scope = Scope(parent=scope)
            attr_scope.define_var('self', self_inst)
            self.visit(attr, attr_scope)

    def build_attr_init(self, node:cool.ProgramNode):
        self.attr_init = dict()
        for classx in node.classes:
            self.attr_init[classx.id] = []
            if classx.parent and not classx.parent in ['IO', 'Object']:
                self.attr_init[classx.id] += self.attr_init[classx.parent]
            for feature in classx.features:
                if type(feature) is cool.AttrDeclarationNode:
                    self.attr_init[classx.id].append(feature)

    @when(cool.ProgramNode)
    def visit(self, node:cool.ProgramNode=None, scope:Scope=None):
        scope = Scope()
        self.build_attr_init(node)
        self.current_function = self.register_function('main')
        instance = self.define_internal_local()
        result = self.define_internal_local()
        self.register_instruction(AllocateNode(instance, 'Main'))
        self.init_class_attr(scope, 'Main', instance)
        self.register_instruction(ArgNode(instance))
        self.register_instruction(StaticCallNode(self.to_function_name('main', 'Main'), result))
        self.register_instruction(CleanArgsNode(1))
        self.register_instruction(ReturnNode(0))
        self.current_function = None

        for classx in node.classes:
            self.visit(classx, scope)
        
        return ProgramNode(self.dottypes, self.dotdata, self.dotcode)
        
    @when(cool.ClassDeclarationNode)
    def visit(self, node:cool.ClassDeclarationNode, scope:Scope):
        self.current_type = self.context.get_type(node.id)

        type_node = self.register_type(node.id)
        type_node.attributes = [ attr.name for attr in self.current_type.get_all_attributes() ]
        type_node.methods = [ (method.name, self.to_function_name(method.name, typex.name))  for method, typex in self.current_type.get_all_methods() ]

        for feature in node.features:
            if isinstance(feature, cool.FuncDeclarationNode):
                self.visit(feature, scope)

        self.current_type = None

    @when(cool.AttrDeclarationNode)
    def visit(self, node:cool.AttrDeclarationNode, scope:Scope):
        result = self.visit(node.expression, scope) if node.expression else 0
        self_inst = scope.get_var('self').local_name
        self.register_instruction(SetAttribNode(self_inst, node.id, result))

    @when(cool.FuncDeclarationNode)
    def visit(self, node:cool.FuncDeclarationNode, scope:Scope):
        func_scope = Scope(parent=scope)
        self.current_method = self.current_type.get_method(node.id)
        type_name = self.current_type.name

        self.current_function = self.register_function(self.to_function_name(self.current_method.name, type_name))
        self_local = self.register_param(VariableInfo('self', None))
        func_scope.define_var('self', self_local)
        for param_name in self.current_method.param_names:
            param_local = self.register_param(VariableInfo(param_name, None))
            func_scope.define_var(param_name, param_local)
        
        body = self.visit(node.expression, func_scope)
        self.register_instruction(ReturnNode(body))

        self.current_method = self.current_function = None


    @when(cool.IfThenElseNode)
    def visit(self, node:cool.IfThenElseNode, scope:Scope):
        if_scope = Scope(parent=scope)
        cond_result = self.visit(node.condition, scope)
        result = self.define_internal_local()
        true_label = self.to_label_name('if_true')
        end_label = self.to_label_name('end_if')
        self.register_instruction(IfGotoNode(cond_result, true_label))
        false_result = self.visit(node.else_body, if_scope)
        self.register_instruction(AssignNode(result, false_result))
        self.register_instruction(GotoNode(end_label))
        self.register_instruction(LabelNode(true_label))
        true_result = self.visit(node.if_body, if_scope)
        self.register_instruction(AssignNode(result, true_result))
        self.register_instruction(LabelNode(end_label))

        return result
        

    @when(cool.WhileLoopNode)
    def visit(self, node:cool.WhileLoopNode, scope:Scope):
        while_scope = Scope(parent=scope)
        loop_label = self.to_label_name('loop')
        body_label = self.to_label_name('body')
        end_label  = self.to_label_name('pool')
        self.register_instruction(LabelNode(loop_label))
        condition = self.visit(node.condition, scope)
        self.register_instruction(IfGotoNode(condition, body_label))
        self.register_instruction(GotoNode(end_label))
        self.register_instruction(LabelNode(body_label))
        self.visit(node.body, while_scope)
        self.register_instruction(LabelNode(end_label))

        return 0


    @when(cool.BlockNode)
    def visit(self, node:cool.BlockNode, scope:Scope):
        result = None
        for expr in node.expressions:
            result = self.visit(expr, scope)
        
        return result


    @when(cool.LetNode)
    def visit(self, node:cool.LetNode, scope:Scope):
        var_name = self.register_local(VariableInfo(node.id, None))
        scope.define_var(node.id, var_name)
        result = self.visit(node.expression, scope) if node.expression else 0

        self.register_instruction(AssignNode(var_name, result))
        
    @when(cool.LetInNode)
    def visit(self, node:cool.LetInNode, scope:Scope):
        let_scope = Scope(parent=scope)
        for let in node.let_body:
            self.visit(let, let_scope)

        result = self.visit(node.in_body, let_scope)
        return result

    @when(cool.CaseNode)
    def visit(self, node:cool.CaseNode, scope:Scope, typex=None, result_inst=None, end_label=None):
        cond = self.define_internal_local()
        not_cond = self.define_internal_local()
        case_label = self.to_label_name(f'case_{node.type}')
        self.register_instruction(ConformNode(cond, typex, node.type))
        self.register_instruction(ComplementNode(not_cond, cond))
        self.register_instruction(IfGotoNode(not_cond, case_label))
        case_scope = Scope(parent=scope)
        case_var = self.register_local(VariableInfo(node.id, None))
        case_scope.define_var(node.id, case_var)
        case_result = self.visit(node.expression, case_scope)
        self.register_instruction(AssignNode(result_inst, case_result))
        self.register_instruction(GotoNode(end_label))
        self.register_instruction(LabelNode(case_label))

    @when(cool.CaseOfNode)
    def visit(self, node:cool.CaseOfNode, scope:Scope):
        order_cases = self.order_caseof(node)
        end_label = self.to_label_name('end')
        error_label = self.to_label_name('error')
        result = self.define_internal_local()
        type_inst = self.define_internal_local()
        is_void = self.define_internal_local()
        obj_inst = self.visit(node.expression, scope)
        self.register_instruction(IsVoidNode(is_void, obj_inst))
        self.register_instruction(IfGotoNode(is_void, error_label))
        self.register_instruction(TypeOfNode(obj_inst, type_inst))
        for case in order_cases:
            self.visit(case, scope, type_inst, result, end_label)
        self.register_instruction(LabelNode(error_label))
        self.register_instruction(ErrorNode())
        self.register_instruction(LabelNode(end_label))

        return result

    @when(cool.AssignNode)
    def visit(self, node:cool.AssignNode, scope:Scope):
        value = self.visit(node.expression, scope)
        pvar = scope.get_var(node.id)
        if not pvar:
            selfx = scope.get_var('self').local_name
            self.register_instruction(SetAttribNode(selfx, node.id, value))
        else:
            pvar = pvar.local_name
            self.register_instruction(AssignNode(pvar, value))
        return 0
    
    @when(cool.MemberCallNode)
    def visit(self, node:cool.MemberCallNode, scope:Scope):
        type_name = self.current_type.name
        result = self.define_internal_local()
        rev_args = []
        for arg in node.args:
            arg_value = self.visit(arg, scope)
            rev_args = [ arg_value ] + rev_args
        for arg_value in rev_args:
            self.register_instruction(ArgNode(arg_value))
        self_inst = scope.get_var('self').local_name
        self.register_instruction(ArgNode(self_inst))
        self.register_instruction(DynamicCallNode(type_name, node.id, result))
        self.register_instruction(CleanArgsNode(len(node.args)+1))

        return result

    @when(cool.FunctionCallNode)
    def visit(self, node:cool.FunctionCallNode, scope:Scope):
        typex = None if not node.type else self.context.get_type(node.type)
        type_name = self.find_type_name(typex, node.id) if typex else ''
        func_name = self.to_function_name(node.id, type_name) if type_name else ''
        result = self.define_internal_local()
        rev_args = []
        for arg in node.args:
            arg_value = self.visit(arg, scope)
            rev_args = [ arg_value ] + rev_args
        for arg_value in rev_args:
            self.register_instruction(ArgNode(arg_value))
        obj_inst = self.visit(node.obj, scope)
        self.register_instruction(ArgNode(obj_inst))
        self.register_instruction(StaticCallNode(func_name, result)) if func_name else self.register_instruction(DynamicCallNode(node.obj.static_type.name, node.id, result))
        self.register_instruction(CleanArgsNode(len(node.args)+1))

        return result
        

    @when(cool.NewNode)
    def visit(self, node:cool.NewNode, scope:Scope): # Remember attributes initialization
        result = self.define_internal_local()
        self.register_instruction(AllocateNode(result, node.type))
        self.init_class_attr(scope, node.type, result)

        return result

    @when(cool.IsVoidNode)
    def visit(self, node:cool.IsVoidNode, scope:Scope):
        body = self.visit(node.expression, scope)
        result = self.define_internal_local()
        
        self.register_instruction(IsVoidNode(result, body))
        return result

    @when(cool.NotNode)
    def visit(self, node:cool.NotNode, scope:Scope):
        value = self.visit(node.expression, scope)
        result = self.define_internal_local()

        self.register_instruction(ComplementNode(result, value))
        return result

    @when(cool.ComplementNode)
    def visit(self, node:cool.ComplementNode, scope:Scope):
        value = self.visit(node.expression, scope)
        result = self.define_internal_local()

        self.register_instruction(ComplementNode(result, value))
        return result

    @when(cool.PlusNode)
    def visit(self, node:cool.PlusNode, scope:Scope):
        left = self.visit(node.left, scope)
        right = self.visit(node.right, scope)
        result = self.define_internal_local()

        self.register_instruction(PlusNode(result, left, right))
        return result

    @when(cool.MinusNode)
    def visit(self, node:cool.MinusNode, scope:Scope):
        left = self.visit(node.left, scope)
        right = self.visit(node.right, scope)
        result = self.define_internal_local()

        self.register_instruction(MinusNode(result, left, right))
        return result

    @when(cool.StarNode)
    def visit(self, node:cool.StarNode, scope:Scope):
        left = self.visit(node.left, scope)
        right = self.visit(node.right, scope)
        result = self.define_internal_local()

        self.register_instruction(StarNode(result, left, right))
        return result

    @when(cool.DivNode)
    def visit(self, node:cool.DivNode, scope:Scope):
        left = self.visit(node.left, scope)
        right = self.visit(node.right, scope)
        result = self.define_internal_local()

        self.register_instruction(DivNode(result, left, right))
        return result

    @when(cool.EqualNode)
    def visit(self, node:cool.EqualNode, scope:Scope):
        left = self.visit(node.left, scope)
        right = self.visit(node.right, scope)
        result = self.define_internal_local()

        if node.left.static_type == self.context.get_type('String'):
            self.register_instruction(StringEqualNode(result, left, right))
        else:
            self.register_instruction(EqualNode(result, left, right))
        return result

    @when(cool.LessNode)
    def visit(self, node:cool.LessNode, scope:Scope):
        left = self.visit(node.left, scope)
        right = self.visit(node.right, scope)
        result = self.define_internal_local()

        self.register_instruction(LessNode(result, left, right))
        return result

    @when(cool.LessEqualNode)
    def visit(self, node:cool.LessEqualNode, scope:Scope):
        left = self.visit(node.left, scope)
        right = self.visit(node.right, scope)
        result = self.define_internal_local()

        self.register_instruction(LessEqNode(result, left, right))
        return result
        
    @when(cool.IdNode)
    def visit(self, node:cool.IdNode, scope:Scope):
        pvar = scope.get_var(node.token)
        if not pvar:
            selfx = scope.get_var('self').local_name
            pvar = self.define_internal_local()

            self.register_instruction(GetAttribNode(pvar, selfx, node.token)) # Perhaps GetAttribNode could need info about self type, this is know in self.current_type variable
        else:
            pvar = pvar.local_name
        return pvar

    @when(cool.BoolNode)
    def visit(self, node:cool.BoolNode, scope:Scope):
       return 1 if node.token.lower() == 'true' else 0

    @when(cool.IntegerNode)
    def visit(self, node:cool.IntegerNode, scope:Scope):
        return int(node.token)

    @when(cool.StringNode)
    def visit(self, node:cool.StringNode, scope:Scope):
        string = self.register_data(node.token[1:-1])
        return string.name
