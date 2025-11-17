"""
Calculator Tool for Context OS.

Provides mathematical computation functionality using SymPy for symbolic and numerical calculations.
"""

import sympy as sp
from typing import Dict, Any, Optional
from utils.logger import get_logger

logger = get_logger('CalculatorTool')


class CalculatorTool:
    """
    CalculatorTool provides mathematical computation using SymPy.

    Features:
    - Arithmetic operations (addition, subtraction, multiplication, division)
    - Algebraic expressions and simplification
    - Symbolic mathematics
    - Trigonometric functions
    - Calculus operations (derivatives, integrals)
    - Equation solving
    - High precision calculations
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize the CalculatorTool.

        Args:
            name: Tool name
            config: Tool configuration from tools.yaml
        """
        self.name = name
        self.config = config
        self.category = 'builtin'

        # Configuration
        self.precision = config.get('precision', 10)


        self.sp = sp
        # Set precision for numerical evaluations
        sp.init_printing()
        logger.info(f"CalculatorTool initialized: {name} (SymPy version {sp.__version__}, precision={self.precision})")

    def execute(self, expression: str, mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluate a mathematical expression.

        Args:
            expression: Mathematical expression to evaluate (e.g., "2 + 2", "sin(pi/2)", "x**2 + 2*x + 1")
            mode: Evaluation mode:
                  - 'numeric' or None: Numerical evaluation (default)
                  - 'symbolic': Keep result in symbolic form
                  - 'simplify': Simplify the expression
                  - 'solve': Solve equation (expression should contain '=')

        Returns:
            dict: Calculation result containing:
                - expression: Original expression
                - result: Calculated result (string representation)
                - numeric_result: Numerical value if applicable
                - mode: Evaluation mode used
                - success: Whether calculation succeeded
                - error: Error message if failed

        Examples:
            >>> calculator.execute("2 + 2")
            {'expression': '2 + 2', 'result': '4', 'numeric_result': 4.0, 'mode': 'numeric', 'success': True}

            >>> calculator.execute("sqrt(2)", mode='numeric')
            {'expression': 'sqrt(2)', 'result': '1.414213562', 'numeric_result': 1.414213562, 'mode': 'numeric', 'success': True}

            >>> calculator.execute("x**2 + 2*x + 1", mode='simplify')
            {'expression': 'x**2 + 2*x + 1', 'result': '(x + 1)**2', 'mode': 'symbolic', 'success': True}
        """
        logger.info(f"Evaluating expression: '{expression}' (mode: {mode or 'numeric'})")

        # Default mode is numeric
        if mode is None:
            mode = 'numeric'

        try:
            # Parse the expression
            parsed_expr = self._parse_expression(expression, mode)

            # Evaluate based on mode
            if mode == 'solve':
                result = self._solve_equation(expression, parsed_expr)
            elif mode == 'simplify':
                result = self._simplify_expression(parsed_expr)
            elif mode == 'symbolic':
                result = self._symbolic_evaluation(parsed_expr)
            else:  # numeric mode (default)
                result = self._numeric_evaluation(parsed_expr)

            logger.info(f"Calculation complete: '{expression}' = {result['result']}")
            return result

        except Exception as e:
            logger.error(f"Calculation failed for '{expression}': {e}")
            return {
                'expression': expression,
                'result': None,
                'mode': mode,
                'error': str(e),
                'success': False
            }

    def _parse_expression(self, expression: str, mode: str) -> Any:
        """
        Parse a mathematical expression string into SymPy expression.

        Args:
            expression: Expression string
            mode: Evaluation mode (affects parsing for 'solve' mode)

        Returns:
            SymPy expression object
        """
        logger.debug(f"Parsing expression: {expression}")

        # For solve mode, handle equations with '='
        if mode == 'solve' and '=' in expression:
            # Split equation into left and right sides
            left, right = expression.split('=', 1)
            left_expr = self.sp.sympify(left.strip())
            right_expr = self.sp.sympify(right.strip())
            # Return equation as left - right = 0
            return left_expr - right_expr
        else:
            # Parse as regular expression
            return self.sp.sympify(expression)

    def _numeric_evaluation(self, expr: Any) -> Dict[str, Any]:
        """
        Evaluate expression numerically.

        Args:
            expr: SymPy expression

        Returns:
            dict: Result dictionary
        """
        # Get numerical value
        numeric_value = float(expr.evalf(self.precision))

        # Format result string based on precision
        if abs(numeric_value) < 1e-10:
            result_str = "0"
        elif abs(numeric_value - int(numeric_value)) < 1e-10:
            result_str = str(int(numeric_value))
        else:
            result_str = f"{numeric_value:.{self.precision}g}"

        return {
            'expression': str(expr),
            'result': result_str,
            'numeric_result': numeric_value,
            'mode': 'numeric',
            'success': True
        }

    def _symbolic_evaluation(self, expr: Any) -> Dict[str, Any]:
        """
        Keep expression in symbolic form.

        Args:
            expr: SymPy expression

        Returns:
            dict: Result dictionary
        """
        result_str = str(expr)

        result_dict = {
            'expression': result_str,
            'result': result_str,
            'mode': 'symbolic',
            'success': True
        }

        # Try to get numeric value if expression is numeric
        try:
            if expr.is_number:
                numeric_value = float(expr.evalf())
                result_dict['numeric_result'] = numeric_value
        except:
            pass

        return result_dict

    def _simplify_expression(self, expr: Any) -> Dict[str, Any]:
        """
        Simplify expression algebraically.

        Args:
            expr: SymPy expression

        Returns:
            dict: Result dictionary
        """
        simplified = self.sp.simplify(expr)
        result_str = str(simplified)

        result_dict = {
            'expression': str(expr),
            'result': result_str,
            'simplified': result_str,
            'mode': 'simplify',
            'success': True
        }

        # Try to get numeric value if expression is numeric
        try:
            if simplified.is_number:
                numeric_value = float(simplified.evalf())
                result_dict['numeric_result'] = numeric_value
        except:
            pass

        return result_dict

    def _solve_equation(self, original_expr: str, expr: Any) -> Dict[str, Any]:
        """
        Solve equation for variables.

        Args:
            original_expr: Original expression string
            expr: SymPy expression (equation in form f(x) = 0)

        Returns:
            dict: Result dictionary with solutions
        """
        # Get free symbols (variables)
        symbols = expr.free_symbols

        if not symbols:
            # No variables, just evaluate
            value = float(expr.evalf())
            if abs(value) < 1e-10:
                result_str = "Equation is satisfied (0 = 0)"
            else:
                result_str = f"Equation is not satisfied ({value} ≠ 0)"

            return {
                'expression': original_expr,
                'result': result_str,
                'mode': 'solve',
                'success': True
            }

        # Solve for the first symbol (or all if multiple)
        solutions = self.sp.solve(expr, symbols)

        # Format solutions
        if not solutions:
            result_str = "No solution found"
        elif isinstance(solutions, dict):
            # Multiple variables
            result_str = ", ".join([f"{var} = {sol}" for var, sol in solutions.items()])
        elif isinstance(solutions, list):
            if len(solutions) == 1:
                result_str = str(solutions[0])
            else:
                result_str = str(solutions)
        else:
            result_str = str(solutions)

        result_dict = {
            'expression': original_expr,
            'result': result_str,
            'solutions': solutions,
            'mode': 'solve',
            'success': True
        }

        # Try to get numeric values for solutions
        try:
            if isinstance(solutions, list) and solutions:
                numeric_solutions = []
                for sol in solutions:
                    if hasattr(sol, 'evalf'):
                        numeric_solutions.append(float(sol.evalf()))
                    else:
                        numeric_solutions.append(sol)
                if numeric_solutions:
                    result_dict['numeric_solutions'] = numeric_solutions
        except:
            pass

        return result_dict

    def get_schema(self) -> Dict[str, Any]:
        """
        Get the parameter schema for this tool.

        Returns:
            dict: Parameter schema
        """
        return {
            'name': self.name,
            'description': 'Calculate mathematical expressions using SymPy. Supports arithmetic, algebra, trigonometry, calculus, and equation solving.',
            'parameters': {
                'expression': {
                    'type': 'string',
                    'description': 'Mathematical expression to evaluate (e.g., "2+2", "sin(pi/2)", "sqrt(16)", "x**2 + 2*x + 1"). Use standard math notation: +, -, *, /, ** (power), sqrt(), sin(), cos(), tan(), log(), exp(), pi, e, etc.',
                    'required': True
                },
                'mode': {
                    'type': 'string',
                    'description': 'Evaluation mode: "numeric" (default, numerical result), "symbolic" (keep symbolic form), "simplify" (simplify expression), "solve" (solve equation, use = in expression)',
                    'required': False,
                    'default': 'numeric',
                    'enum': ['numeric', 'symbolic', 'simplify', 'solve']
                }
            },
            'required': ['expression']
        }
