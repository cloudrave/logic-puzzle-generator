import abc
import itertools
import operator
import logging

logger = logging.getLogger(__name__)

DEBUG = True
if DEBUG:
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())


class CharacterIdentifierError(Exception):
    pass


class TooManyMonksError(Exception):
    def __init__(self, monk_count):
        self.message = "You asked for {} Monks, which is too many here.".format(monk_count)

    def __repr__(self):
        return self.message


class Character:
    title = '---Not Set---'
    short_identifier = '_'
    truth_quantifier = '_'

    def __str__(self):
        return "{}".format(self.title)

    def tells_truth_more_often_than(self, character):
        return self.truth_quantifier > character.truth_quantifier

    def tells_truth_less_often_than(self, character):
        return self.truth_quantifier < character.truth_quantifier

    def tells_truth_at_least_as_often_as(self, character):
        return self.truth_quantifier >= character.truth_quantifier

    def tells_truth_less_often_or_the_same_as(self, character):
        return self.truth_quantifier <= character.truth_quantifier


class Knight(Character):
    title = 'Knight'
    short_identifier = 'K'
    truth_quantifier = 1


class Monk(Character):
    title = 'Monk'
    short_identifier = 'M'
    truth_quantifier = 0


class Knave(Character):
    title = 'Knave'
    short_identifier = 'V'
    truth_quantifier = -1


POSSIBLE_CHARACTERS = [Knight, Knave, Monk]


class Scenario:
    def __init__(self, puzzle, character_types: {str: type}):
        self.puzzle = puzzle  # type: Puzzle
        self.character_types = character_types
        self.result = None  # Will be set after consistency is evaluated.

    def _check_consistency(self):
        """
        If it makes sense that each character would speak their respective phrases, returns True; otherwise False.

        If False, returns a reason.

        :rtype: (bool, str)
        :returns: (is_consistent, reason)
        """
        for character_name, statements in self.puzzle.character_statements.items():
            speaking_character_type = self.character_types[character_name]

            # In order to simplify the complexity of nested statements for debugging, we try not to over-encapsulate.
            statement_count = len(statements)
            if statement_count == 0:
                continue
            elif statement_count == 1:
                statement = statements[0]
            else:  # statement_count > 1
                # Note: All statements this character says must make sense independently.
                statement = ConjunctiveStatement(*statements)

            if statement.evaluate_consistency(speaking_character_type=speaking_character_type, scenario=self) is False:
                return False, '{} should not have said "{}".'.format(character_name, statement)
        return True, None

    def check_consistency(self):
        result = self._check_consistency()
        self.result = result
        return result

    def __eq__(self, other):
        """
        To be equal, two Scenario instances must only have the same character name-type assignments and character count.
        """
        assert(isinstance(other, Scenario))
        if len(self.character_types) != len(other.character_types):
            return False
        for name, t in self.character_types.items():
            if other.character_types[name] != t:
                return False
        return True

    def __hash__(self):
        """
        TODO: This could be more efficient and less stupid.  ;)
        """
        character_string = "|"
        for name, t in self.character_types.items():
            character_string += "{},{}|".format(name, t.short_identifier)
        return hash(character_string)

    def __str__(self, joiner=" \t "):
        names_and_identities = []
        for name, character_type in self.character_types.items():
            names_and_identities.append("{}={}".format(name, character_type.short_identifier))
        return joiner.join(names_and_identities)

    def __repr__(self):
        return "<Scenario: {}>".format(self.__str__(joiner=', '))


class Statement:
    def evaluate_consistency(self, speaking_character_type, scenario: Scenario):
        logger.debug('Evaluating consistency of "{}" as {}'.format(self, speaking_character_type.title))
        if speaking_character_type == Monk:
            return True
        truth = self.evaluate_truth(scenario=scenario)
        if speaking_character_type == Knight:
            return truth
        if speaking_character_type == Knave:
            return not truth

    @abc.abstractmethod
    def evaluate_truth(self, scenario: Scenario) -> True | False:
        pass

    @abc.abstractmethod
    def as_sentence(self):
        pass

    def __str__(self):
        return '{}'.format(self.as_sentence())

    def __repr__(self):
        return "<{}: {}>".format(type(self).__name__, str(self))


class AbstractStatementCombiner(Statement):
    joining_string = " --- "

    @abc.abstractmethod
    def for_each_statement(self, truth_value):
        """
        If returns None, loop will continue.  If returns other, evaluation is finished with this final value.
        :return: True | False | None
        """
        raise NotImplementedError

    @abc.abstractmethod
    def default_value(self):
        """
        :return: True | False
        """
        raise NotImplementedError

    def __init__(self, *statements: [Statement]):
        self.statements = statements

    def evaluate_truth(self, scenario: Scenario):
        logger.debug("Evaluating truth of [{}] ".format(self))
        for statement in self.statements:
            truth = statement.evaluate_truth(scenario=scenario)
            result = self.for_each_statement(truth_value=truth)
            if result is not None:
                return result
        return self.default_value()

    def __str__(self):
        return " AND ".join(map(lambda s: '({})'.format(s), self.statements))


class ConjunctiveStatement(AbstractStatementCombiner):
    """
    Requires every statement to be true.  If no statements, value is true.
    """
    joining_string = ' AND '

    def for_each_statement(self, truth_value):
        if truth_value is False:
            return False
        return None

    def default_value(self):
        return True


class DisjunctiveStatement(AbstractStatementCombiner):
    """
    Requires at least one statement to be true.  If no statements, value is false.
    """
    joining_string = ' OR '

    def for_each_statement(self, truth_value):
        if truth_value is True:
            return True
        return None

    def default_value(self):
        return False


class Not(Statement):
    def __init__(self, statement: Statement):
        self.statement = statement

    def evaluate_truth(self, scenario: Scenario):
        truth = self.statement.evaluate_truth(scenario=scenario)
        return not truth

    def __str__(self):
        return "NOT({})".format(self.statement)


class IsOfType(Statement):
    def __init__(self, target_name: str, claimed_character_type):
        self.target_name = target_name
        self.claimed_character_type = claimed_character_type

    def evaluate_truth(self, scenario: Scenario):
        try:
            return isinstance(scenario.character_types[self.target_name], self.claimed_character_type)
        except KeyError:
            raise CharacterIdentifierError("Cannot find character '{}'.".format(self.target_name))

    def as_sentence(self):
        return "{} is a {}.".format(self.target_name, self.claimed_character_type.title)


def english_operator_helper(relation):
    if relation == operator.eq:
        return 'exactly'
    elif relation == operator.lt:
        return 'fewer than'
    elif relation == operator.gt:
        return 'more than'
    elif relation == operator.le:
        return 'fewer than or exactly'
    elif relation == operator.ge:
        return 'more than or exactly'
    else:
        raise Exception("Cannot handle operator of type {}.".format(relation))


class CountOfType(Statement):
    def __init__(self, character_type, claimed_count: int, claimed_relation):
        self.character_type = character_type
        self.claimed_count = claimed_count
        self.claimed_relation = claimed_relation

    def evaluate_truth(self, scenario: Scenario):
        count = 0
        for t in scenario.character_types.values():
            if t == self.character_type:
                count += 1
        return self.claimed_relation(count, self.claimed_count)

    def as_sentence(self):
        return "There are {op} {count} {kind}s.".format(
            op=english_operator_helper(self.claimed_relation),
            count=self.claimed_count,
            kind=self.character_type.title,
        )


class SamenessCount(Statement):
    def __init__(self, claimed_count: int, claimed_relation):
        self.claimed_count = claimed_count
        self.claimed_relation = claimed_relation

        satisfying_statements = []
        for kind in POSSIBLE_CHARACTERS:
            satisfying_statements.append(
                CountOfType(kind, self.claimed_count, self.claimed_relation)
            )
        self.disjunctive_statement = DisjunctiveStatement(*satisfying_statements)

    def evaluate_truth(self, scenario: Scenario):
        """
        If one of the possible character types satisfies this statement, then it is true.
        """
        return self.disjunctive_statement.evaluate_truth(scenario=scenario)

    def as_sentence(self):
        return "{op} {count} of us are the same.".format(
            op=english_operator_helper(self.claimed_relation),
            count=self.claimed_count,
        )


class Puzzle:
    def __init__(self, character_names_and_statements: {str: [Statement]}):
        self.scenarios = []
        self.character_names = []
        self.character_statements = {}

        for character_name, statements in character_names_and_statements.items():
            self.character_names.append(character_name)
            self.character_statements[character_name] = statements

        self.max_num_monks = self._calculate_max_num_monks()

    @property
    def num_characters(self):
        return len(self.character_names)

    def _calculate_max_num_monks(self):
        """
        Determines the maximum number of Monks allowed in a puzzle of this size.
        (Less than half the number of characters.)
        """
        max_num_monks = self.num_characters // 2
        if max_num_monks == self.num_characters / 2:
            max_num_monks -= 1
        return max_num_monks

    def _generate_scenario(self, identity_ordering: [type]):
        """
        Generates a scenario, rejecting a scenario with too many Monks.
        """
        character_types = {}
        i = 0
        monk_count = 0
        for name in self.character_names:
            if identity_ordering[i] == Monk:
                monk_count += 1
            character_types[name] = identity_ordering[i]
            if monk_count > self.max_num_monks:
                raise TooManyMonksError(monk_count)
            i += 1
        return Scenario(puzzle=self, character_types=character_types)

    def _generate_scenarios(self):
        self.scenarios = []  # Clears all scenarios first.
        for identity_ordering in itertools.product(POSSIBLE_CHARACTERS, repeat=self.num_characters):
            try:
                scenario = self._generate_scenario(identity_ordering)
            except TooManyMonksError:
                continue
            self.scenarios.append(scenario)

    def check_scenario(self, scenario, should_print=False):
        result, reason = scenario.check_consistency()
        if should_print:
            if result:
                print('+++++ \t{}'.format(scenario))
            else:
                if DEBUG is True:
                    print('----- \t{} \t ---> {}'.format(scenario, reason))

    def generate_and_check_scenarios(self, should_print=False):
        self._generate_scenarios()
        for scenario in self.scenarios:
            self.check_scenario(scenario=scenario, should_print=should_print)

    def get_consistent_scenario_set(self):
        ret = set()
        for scenario in self.scenarios:
            if scenario.result[0] is True:
                ret.add(scenario)
        return ret

    def __str__(self):
        return self.character_names
