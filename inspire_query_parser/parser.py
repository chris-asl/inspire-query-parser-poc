# -*- coding: utf-8 -*-
#
# This file is part of INSPIRE.
# Copyright (C) 2014-2017 CERN.
#
# INSPIRE is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# INSPIRE is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with INSPIRE. If not, see <http://www.gnu.org/licenses/>.
#
# In applying this license, CERN does not waive the privileges and immunities
# granted to it by virtue of its status as an Intergovernmental Organization
# or submit itself to any jurisdiction.

from __future__ import unicode_literals, print_function

from pypeg2 import attr, Keyword, Literal, omit, optional, re, K, Enum, contiguous, maybe_some, some, GrammarValueError, \
    whitespace

from . import ast
from .config import INSPIRE_PARSER_KEYWORDS, INSPIRE_KEYWORDS_SET
from .utils.utils import string_types


# #### Parser customization ####
class CaseInsensitiveKeyword(Keyword):
    """Supports case insensitive keywords

    All subtypes must declare a grammar attribute with an Enum of accepted keywords/literals.
    """
    def __init__(self, keyword):
        """Adds lowercase keyword to the keyword table."""
        try:
            self.grammar
        except AttributeError:
            raise GrammarValueError(self.__class__.__name__ + " expects a grammar attribute (Enum).")
        keyword = keyword.lower()
        if keyword not in Keyword.table:
            Keyword.table[keyword] = self
        self.name = keyword

    @classmethod
    def parse(cls, parser, text, pos):
        """Checks if terminal token is a keyword after lower-casing it."""
        m = cls.regex.match(text)
        if m:
            # Check if match is is not in the grammar of the specific keyword class.
            if m.group(0).lower() not in cls.grammar:
                result = text, SyntaxError(repr(m.group(0)) + " is not a member of " + repr(cls.grammar))
            else:
                result = text[len(m.group(0)):], cls(m.group(0))
        else:
            result = text, SyntaxError("expecting " + repr(cls.__name__))
        return result

CIKeyword = CaseInsensitiveKeyword

u_word = re.compile("\w+", re.UNICODE)
# ########################


class BooleanOperator(Enum):
    """Serves as the possible case for a boolean operator."""
    AND = 'and'
    OR = 'or'


class LeafRule(ast.Leaf):
    def __init__(self):
        pass


class UnaryRule(ast.UnaryOp):
    def __init__(self):
        pass


class BinaryRule(ast.BinaryOp):
    def __init__(self):
        pass


class ListRule(ast.ListOp):
    def __init__(self, children):
        super(ListRule, self).__init__(children)
# ########################


# #### Keywords ####
class And(CIKeyword):
    """
    The reason for defining an Enum grammar of Keywords is for populating the Keyword.table for checking whether
    terminal symbols are actually DSL keywords.
    """
    regex = re.compile(r"(and|\+|&)", re.IGNORECASE)
    grammar = Enum(K("and"), K("+"), K("&"))


class Or(CIKeyword):
    """
    The reason for defining an Enum grammar of Keywords is for populating the Keyword.table for checking whether
    terminal symbols are actually DSL keywords.
    """
    regex = re.compile(r"(or|\|)", re.IGNORECASE)
    grammar = Enum(K("or"), K("|"))


class Not(CIKeyword):
    """
    The reason for defining an Enum grammar of Keywords is for populating the Keyword.table for checking whether
    terminal symbols are actually DSL keywords.
    """
    regex = re.compile(r"(not|-)", re.IGNORECASE)
    grammar = Enum(K("not"), K("-"))
# ########################


# #### Lowest level operators #####
class InspireKeyword(LeafRule):
    grammar = re.compile(r"({0})(?=(:|\s))".format("|".join(INSPIRE_PARSER_KEYWORDS.keys())))

    def __init__(self, value):
        self.value = INSPIRE_PARSER_KEYWORDS[value]


class SimpleValueUnit(LeafRule):
    """Represents either a terminal symbol (without parentheses) or a parenthesized SimpleValue.

    The parenthesized case (2nd option of SimpleValueUnit) accepts a SimpleValue which is the more generic case of
    plaintext and in turn (its grammar) encapsulates whitespace and SimpleValueUnit recognition.

    """
    token_regex = re.compile(r"[^\s:)(]+", re.UNICODE)

    arxiv_token_regex = re.compile(r"arxiv:" + token_regex.pattern, re.IGNORECASE)
    """Arxiv identifiers are special cases of tokens where the ":" symbol is allowed."""

    date_specifiers_regex = re.compile(r"(yesterday|today|(this\s+month)|(last\s+month))\s*-\s*\d+", re.UNICODE)

    parenthesized_token_grammar = None  # is set after SimpleValue definition.

    starts_with_colon = re.compile(r"\s*:", re.UNICODE)
    """Used for recognizing whether terminal token is a keyword (i.e. followed by some whitespace and ":"."""

    def __init__(self, args):
        super(SimpleValueUnit, self).__init__()
        if isinstance(args, string_types):
            # Value was recognized by the 1st option of the list grammar (regex)
            self.value = args
        else:
            # Value was recognized by the 2nd option of the list grammar
            self.value = args[0] + args[1].value + args[2]

    @classmethod
    def parse_terminal_token(cls, parser, text):
        """Parses a terminal token that doesn't contain parentheses nor colon symbol.

        Note:
            If we're parsing text not in parentheses, then some DSL keywords (e.g. And, Or, Not, defined above) should
            not be recognized as terminals, thus we check if they are in the Keywords table (namespace like structure
            handled by PyPeg).
            This is done only when we are not parsing a parenthesized SimpleValue.

            Also, helps in supporting more implicit-and queries cases (last two checks).
        """
        m = cls.token_regex.match(text)
        if m:
            # Check if token is a DSL keyword. Disable this check in the case where the parser isn't parsing a
            # parenthesized terminal.
            if not parser.parsing_parenthesized_terminal and m.group().lower() in Keyword.table:
                return text, SyntaxError("found DSL keyword: " + m.group(0))

            t = text[len(m.group(0)):]

            # Attempt to recognize whether current terminal is followed by a ":", which definitely signifies that
            # we are parsing a keyword, and we shouldn't.
            if cls.starts_with_colon.match(t):
                return text, \
                       SyntaxError("parsing a keyword (token followed by \":\"): \"" + repr(m.group(0)) + "\"")

            # Attempt to recognize whether current terminal is a non shortened version of an Inspire keywords. This is
            # done for supporting implicit-and in case of SPIRES style keyword queries. Using the non shortened version
            # of the keywords, makes this recognition not eager.
            if not parser.parsing_parenthesized_simple_values_expression \
                    and m.group() in INSPIRE_KEYWORDS_SET:
                return text, SyntaxError("parsing a keyword (non shortened INSPIRE keyword)")

            result = t, m.group(0)
        else:
            result = text, SyntaxError("expecting match on " + repr(cls.token_regex.pattern))
        return result

    @classmethod
    def parse(cls, parser, text, pos):
        """Imitates parsing a list grammar.

        Specifically, this
        grammar = [
            SimpleValueUnit.date_specifiers_regex,
            SimpleValueUnit.arxiv_token_regex,
            SimpleValueUnit.token_regex,
            SimpleValueUnit.parenthesized_token_grammar
        ].

        Parses plaintext which matches date specifiers or arxiv_identifier syntax, or is comprised of either 1) simple
        terminal (no parentheses) or 2) a parenthesized SimpleValue.

        For example, "e(+)" will be parsed in two steps, first, "e" token will be recognized and then "(+)", as a
        parenthesized SimpleValue.
        """
        found = False

        # Attempt to parse date specifier
        m = cls.date_specifiers_regex.match(text)
        if m:
            t, r, found = text[len(m.group(0)):], m.group(0), True
        else:
            # Attempt to parse arxiv identifier
            m = cls.arxiv_token_regex.match(text)
            if m:
                t, r, found = text[len(m.group(0)):], m.group(0), True
            else:
                # Attempt to parse a terminal token
                t, r = SimpleValueUnit.parse_terminal_token(parser, text)
                if type(r) != SyntaxError:
                    found = True
                else:
                    # Attempt to parse a terminal with parentheses
                    try:
                        # Enable parsing a parenthesized terminal so that we can accept {+, -, |} as terminals.
                        parser.parsing_parenthesized_terminal = True
                        t, r = parser.parse(text, cls.parenthesized_token_grammar, pos)

                        found = True
                    except SyntaxError:
                        pass
                    except GrammarValueError:
                        raise
                    except ValueError:
                        pass
                    finally:
                        parser.parsing_parenthesized_terminal = False

        if found:
            result = t, SimpleValueUnit(r)
        else:
            result = text, SyntaxError("expecting match on " + cls.__name__)

        return result


class SimpleValue(LeafRule):
    """Represents terminals as plaintext.

    E.g. title top cross section, or title Si-28(p(pol.), n(pol.)).
    """
    class Whitespace(LeafRule):
        grammar = attr('value', whitespace)

    grammar = contiguous(SimpleValueUnit, maybe_some((optional(Whitespace), some(SimpleValueUnit))))

    def __init__(self, values):
        super(SimpleValue, self).__init__()
        self.value = unicode.strip(''.join([v.value for v in values]))

    @classmethod
    def parse(cls, parser, text, pos):

        def unconsume_and_reconstruct_input():
            """Reconstruct input in case of consuming a keyword query with ComplexValue as SimpleValue.

            Un-consuming 3 elements and specifically a Keyword, Whitespace and ComplexValue and then reconstructing 
            parser's input text.

            Example:
                Given this query "author foo t 'bar'", r would be:
                    r = [SimpleValueUnit("foo"), Whitespace(" "), SimpleValueUnit("t"), Whitespace(" "),
                        SimpleValueUnit("'bar'")]
                thus after this method, r would be [SimpleValueUnit("foo"), Whitespace(" ")], while initial text will
                have been reconstructed as "t 'bar' rest_of_the_text".
            """
            reconstructed_terminals = r[:idx - 2]
            remaining_text = ''.join([v.value for v in r[idx - 2:]]) + " " + t
            return remaining_text, reconstructed_terminals

        try:
            t, r = parser.parse(text, cls.grammar)

            # Covering a case of implicit-and when one of the SimpleValue tokens is a ComplexValue.
            # E.g. with the query "author foo t 'bar'", since 'bar' is a ComplexValue, then the previous token is a
            # keyword. This means we have consumed a KeywordQuery (due to 'and' missing).
            found_complex_value = False
            for idx, v in enumerate(r):
                if ComplexValue.regex.match(v.value):
                    remaining_text, reconstructed_terminals = unconsume_and_reconstruct_input(r)
                    found_complex_value = True
                    break

            if found_complex_value:
                result = remaining_text, SimpleValue(reconstructed_terminals)
            else:
                result = t, SimpleValue(r)

        except SyntaxError as e:
            return text, e

        return result


SimpleValueUnit.parenthesized_token_grammar = (re.compile(r"\("), SimpleValue, re.compile(r"\)"))


# ################################################## #
# Boolean operators support at SimpleValues level
# ################################################## #
class SimpleValueNegation(UnaryRule):
    """Negation accepting only SimpleValues."""
    grammar = omit(Not), attr('op', SimpleValue)


class SimpleValueBooleanQuery(BinaryRule):
    """For supporting queries like author:(foo or bar and not foobar)."""
    bool_op = None

    def __init__(self, args):
        self.left = args[0]

        if isinstance(args[1], And):
            self.bool_op = BooleanOperator.AND
        elif isinstance(args[1], Or):
            self.bool_op = BooleanOperator.OR
        else:
            raise ValueError("Unexpected boolean operator: " + repr(args[1]))

        self.right = args[2]

    @classmethod
    def parse(cls, parser, text, pos):
        # Used to check whether we parsed successfully up to
        left_operand, operator = None, None
        try:
            # Parse left operand
            text_after_left_op, left_operand = parser.parse(text, cls.grammar[0])

            # Parse boolean operators
            text_after_bool_op, operator = parser.parse(text_after_left_op, cls.grammar[1])

            # Parse right operand.
            # We don't want to eagerly recognize keyword queries as SimpleValues.
            # So we attempt to firstly recognize the more specific rules (keyword queries and their negation), and
            # then a SimpleValue.
            _ = parser.parse(text_after_bool_op, (omit(optional(Not)), [InvenioKeywordQuery, SpiresKeywordQuery]))

            # Keyword query parsing succeeded, stop boolean_op among terminals recognition.
            result = text, SyntaxError("found keyword query at terminals level")

        except SyntaxError as e:
            result = text, e

            if left_operand and operator:
                    # Attempt to parse a right operand
                    try:
                        t, right_operand = parser.parse(text_after_bool_op, cls.grammar[2])
                        result = t, SimpleValueBooleanQuery([left_operand, operator, right_operand])
                    except SyntaxError as e:  # Actual failure of parsing boolean query at terminals level
                        return text, e

        return result


SimpleValueBooleanQuery.grammar = (
    # Left operand options
    [
        SimpleValueNegation,
        SimpleValue,
    ],

    [And, Or],

    # Right operand options
    [
        SimpleValueBooleanQuery,
        SimpleValueNegation,
        SimpleValue,
    ]
)


class ParenthesizedSimpleValues(UnaryRule):
    """Parses parenthesized simple values along with boolean operations on them."""
    grammar = omit(Literal("(")), [SimpleValueBooleanQuery, SimpleValueNegation, SimpleValue], omit(Literal(")"))

    @classmethod
    def parse(cls, parser, text, pos):
        """Using our own parse to enable the flag below."""
        try:
            parser.parsing_parenthesized_simple_values_expression = True
            t, r = parser.parse(text, cls.grammar)
            return t, r
        except SyntaxError as e:
            return text, e
        finally:
            parser.parsing_parenthesized_simple_values_expression = False
# ######################################## #


class ComplexValue(LeafRule):
    """Accepting value with either single/double quotes or a regex value (/^.../$).

    These values have special and different meaning for the later phases of parsing:
      * Single quotes: partial text matching (text is analyzed before searched)
      * Double quotes: exact text matching
      * Regex: regex searches

    E.g. t 'Millisecond pulsar velocities'.

    This makes no difference for the parser and will be handled at a later parsing phase.
    """
    regex = re.compile(r"((/.+?/)|('.*?')|(\".*?\"))")
    grammar = attr('value', regex)


class SimpleRangeValue(LeafRule):
    grammar = attr('value', re.compile(r"([^\s)(-]|-+[^\s)(>])+"))


class GreaterThanOp(UnaryRule):
    """Greater than operator.

    Supports queries like author-count > 2000 or date after 10-2000.
    """
    grammar = omit(re.compile(r"after|>", re.IGNORECASE)), attr('op', SimpleValue)


class GreaterEqualOp(UnaryRule):
    """Greater than or Equal to operator.

    Supports queries like date >= 10-2000 or topcite 200+.
    """
    grammar = [
        (omit(Literal(">=")), attr('op', SimpleValue)),
        # Accept a number or anything that doesn't contain {whitespace, (, ), :} followed by a "-" which should be
        # followed by \s or ) or end of input so that you don't accept a value that is 1-e.
        (attr('op', re.compile(r"\d+")), omit(re.compile(r'\+(?=\s|\)|$)'))),
        (attr('op', re.compile(r"[^\s():]+(?=([ ]+\+|\+))")), omit(re.compile(r'\+(?=\s|\)|$)'))),
    ]


class LessThanOp(UnaryRule):
    """Less than operator.

    Supports queries like author-count < 100 or date before 1984.
    """
    grammar = omit(re.compile(r"before|<", re.IGNORECASE)), attr('op', SimpleValue)


class LessEqualOp(UnaryRule):
    """Less than or Equal to operator.

    Supports queries like date <= 10-2000 or author-count 100-.
    """
    grammar = [
        (omit(Literal("<=")), attr('op', SimpleValue)),
        # Accept a number or anything that doesn't contain {whitespace, (, ), :} followed by a "-" which should be
        # followed by \s or ) or end of input so that you don't accept a value that is 1-e.
        (attr('op', re.compile(r"\d+")), omit(re.compile(r'-(?=\s|\)|$)'))),
        (attr('op', re.compile(r"[^\s():]+(?=( -|-))")), omit(re.compile(r'\+(?=\s|\)|$)'))),

    ]


class RangeOp(BinaryRule):
    """Range operator mixing any type of values.

    E.g.    muon decay year:1983->1992
            author:"Ellis, J"->"Ellis, Qqq"
            author:"Ellis, J"->Ellis, M

    The non symmetrical type of values will be handled at a later phase.
    """
    grammar = \
        attr('left', [ComplexValue, SimpleRangeValue]), \
        omit(Literal("->")), \
        attr('right', [ComplexValue, SimpleRangeValue])


class Value(UnaryRule):
    """Generic rule for all kinds of phrases recognized.

    Serves as an encapsulation of the listed rules.
    """
    grammar = attr('op', [
        (omit(Literal("=")), SimpleValue),
        RangeOp,
        GreaterEqualOp,
        LessEqualOp,
        GreaterThanOp,
        LessThanOp,
        ComplexValue,
        ParenthesizedSimpleValues,
        SimpleValueBooleanQuery,
        SimpleValue,
    ])
########################


class InvenioKeywordQuery(BinaryRule):
    """Keyword queries with colon separator (i.e. Invenio style).

    There needs to be a distinction between Invenio and SPIRES keyword queries, so as the parser is able to recognize
    any terminal as keyword for the former ones.

    Note:
        "arxiv:arxiv_identifier" should be excluded from the generic keyword pattern as it is a special case of
        SimpleValue, since it contains ":".
    E.g. author: ellis, title: boson, or unknown_keyword: foo.
    """
    grammar = attr('left', [InspireKeyword, re.compile(r"(?!arxiv)[^\s:]+")]), \
        omit(':'), \
        attr('right', Value)


class SpiresKeywordQuery(BinaryRule):
    """Keyword queries with space separator (i.e. Spires style)."""
    grammar = attr('left', InspireKeyword), attr('right', Value)


class SimpleQuery(UnaryRule):
    """Query basic units.

    These are comprised of metadata queries, keywords and value queries.
    """
    grammar = attr('op', [
        InvenioKeywordQuery,
        SpiresKeywordQuery,
        Value,
    ])


class Statement(UnaryRule):
    """The most generic query component.

    Supports queries chaining, see its grammar for more information.
    """
    pass


class Expression(UnaryRule):
    """A generic query expression.

    Serves as a more restrictive rule than Statement.
    This is useful for eliminating left recursion in the grammar (requirement for PEGs) when used in binary queries as
    left hand side production rule.
    """
    pass


class NotQuery(UnaryRule):
    """Negation query."""
    grammar = omit(Not), attr('op', Expression)


class ParenthesizedQuery(UnaryRule):
    """Parenthesized query for denoting precedence."""
    grammar = omit(Literal('(')), attr('op', Statement), omit(Literal(')'))


class NestedKeywordQuery(BinaryRule):
    """Nested Keyword queries.

    E.g. citedby:author:hui and refersto:author:witten
    """
    pass


Expression.grammar = attr('op', [
    NotQuery,
    NestedKeywordQuery,
    ParenthesizedQuery,
    SimpleQuery,
])


NestedKeywordQuery.grammar = \
    attr('left', [
        # Most specific regex must be higher.
        re.compile(r'citedbyexcludingselfcites', re.IGNORECASE),
        re.compile(r'citedbyx', re.IGNORECASE),
        re.compile(r'citedby', re.IGNORECASE),
        re.compile(r'referstoexcludingselfcites', re.IGNORECASE),
        re.compile(r'referstox', re.IGNORECASE),
        re.compile(r'refersto', re.IGNORECASE),
    ]), \
    optional(omit(":")), \
    attr('right', Expression)


class BooleanQuery(BinaryRule):
    """Represents boolean query as a binary rule.

    Attributes:
        bool_op (str): Representation of the actual boolean operator.
            If its value is None at creation time, this signifies an Implicit And. From that point on, this attribute
            will contain the value from :attr:`BooleanOperator.AND` field.
    """
    bool_op = None
    grammar = Expression, [And, Or, None], Statement

    def __init__(self, args):
        self.left = args[0]

        if len(args) == 3:
            if isinstance(args[1], And):
                self.bool_op = BooleanOperator.AND
            elif isinstance(args[1], Or):
                self.bool_op = BooleanOperator.OR
            else:
                raise ValueError("Unexpected boolean operator: " + repr(args[1]))
        else:  # Implicit-And query
            self.bool_op = BooleanOperator.AND

        self.right = args[len(args) - 1]
# ########################


# #### Main productions ####
Statement.grammar = attr('op', [BooleanQuery, Expression])


class MalformedQueryText(LeafRule):
    """Represents queries that weren't recognized by the main parsing branch of Statements."""
    grammar = some(re.compile(r"[^\s]+", re.UNICODE))

    def __init__(self, values):
        self.value = ' '.join([v for v in values])


class EmptyQuery(LeafRule):
    grammar = omit(optional(whitespace)), attr('value', None)


class Query(ListRule):
    """The entry-point for the grammar.

    Find keyword is ignored as the current grammar is an augmentation of SPIRES and Invenio style syntaxes.
    It only serves for backward compatibility with SPIRES syntax.
    """
    grammar = [
        (omit(optional(re.compile(r"(find|fin|fi|f)\s", re.IGNORECASE))),
         (Statement, maybe_some(MalformedQueryText))),
        MalformedQueryText,
        EmptyQuery,
    ]
