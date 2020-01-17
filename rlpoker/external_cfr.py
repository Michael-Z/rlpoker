"""
This module implements external-sampling MCCFR. See Lanctot et al. - Monte Carlo Sampling for Regret Minimisation in
Extensive Games.
"""

from typing import Any, List, Dict

from rlpoker import extensive_game
from rlpoker import cfr_game
from rlpoker import cfr_util
from rlpoker import best_response
from rlpoker import cfr_metrics


def external_sampling_cfr(game: extensive_game.ExtensiveGame, num_iters: int = 1000):
    """

    Args:
        game: ExtensiveGame.
        num_iters: int. The number of iterations of CFR to perform.

    Returns:
        average_strategy
        exploitabilities
        strategies
    """
    # regrets is a dictionary where the keys are the information sets and values
    # are dictionaries from actions available in that information set to the
    # counterfactual regret for not playing that action in that information set.
    # Since information sets encode the player, we only require one dictionary.
    regrets = dict()

    # Strategy_t holds the strategy at time t; similarly strategy_t_1 holds the
    # strategy at time t + 1.
    strategy_t = extensive_game.Strategy.initialise()
    strategy_t_1 = extensive_game.Strategy.initialise()

    average_strategy = cfr_util.AverageStrategy(game)

    strategies = []
    exploitabilities = []

    for t in range(num_iters):
        for player in [1, 2]:
            external_sampling_cfr_recursive(game, game.root, player, regrets, strategy_t, strategy_t_1)

        # Update the strategies
        strategy_t = strategy_t_1.copy()
        strategies.append(game.complete_strategy_uniformly(strategy_t))

        # Compute the average strategy
        if t % 200 == 0:
            # Update average strategy
            completed_strategy = game.complete_strategy_uniformly(strategy_t)
            cfr_util.update_average_strategy(game, average_strategy, completed_strategy)

            # Compute exploitability
            completed_average_strategy = game.complete_strategy_uniformly(average_strategy.compute_strategy())
            exploitability = best_response.compute_exploitability(game, completed_average_strategy)
            exploitabilities.append((t, exploitability))

            print("t: {}, exploitability: {} mbb/h".format(t, exploitability * 1000))

            cumulative_immediate_regrets, all_immediate_regrets = cfr_metrics.compute_immediate_regret(
                game, strategies)
            print("Cumulative immediate regrets: {}".format(cumulative_immediate_regrets))

    return average_strategy.compute_strategy(), exploitabilities, strategies


def external_sampling_cfr_recursive(
        game: extensive_game.ExtensiveGame,
        node: extensive_game.ExtensiveGameNode,
        player: int,
        regrets: Dict,
        strategy_t: extensive_game.Strategy,
        strategy_t_1: extensive_game.Strategy,
):
    """
    Computes the 'expected player utility' sum_{z in Q and Z_I} pi_i^sigma (z[I], z) u_i(z). Samples the actions of
    chance nodes and the nodes of the other players. Accumulates the immediate sampled counterfactual regret:

    rtilde(I, a) = sum_{z in Q and Z_I} u_i(z) (pi_i^sigma(z[I]a, z) - pi_i^sigma(z[I], z)).

    Args:
        game:
        node:
        player:
        regrets:
        strategy_t: the strategy used at time t. We don't update this one.
        strategy_t_1: the strategy to use at time t + 1. We update this one in this function call.

    Returns:
        expected_player_utility
    """
    if node.player == -1:
        # Terminal node. Just return the utility to the player.
        return node.utility[player]
    elif node.player == 0:
        # Chance player. We sample an action and then return the expected utility for that action.
        a = cfr_game.sample_chance_action(node)
        return external_sampling_cfr_recursive(
            game,
            node.children[a],
            player,
            regrets,
            strategy_t,
            strategy_t_1)
    elif node.player == player:
        # Return sum_{z in Q and Z_I} pi_i^sigma (z[I], z) u_i(z)

        expected_utilities = dict()
        action_probs = dict()
        information_set = cfr_game.get_information_set(game, node)
        expected_utility = 0.0
        if information_set not in strategy_t.get_info_sets():
            strategy_t.set_uniform_action_probs(information_set, list(node.children.keys()))

        immediate_regrets = dict()
        for action, child in node.children.items():
            expected_utilities[action] = external_sampling_cfr_recursive(
                game, child, player, regrets, strategy_t, strategy_t_1)
            action_probs[action] = strategy_t[information_set][action]

            expected_utility += action_probs[action] * expected_utilities[action]

            # Update the regrets.
            immediate_regrets[action] = (1 - action_probs[action]) * expected_utilities[action]

        if information_set not in regrets:
            regrets[information_set] = extensive_game.ActionFloat(immediate_regrets)
        else:
            regrets[information_set] = extensive_game.ActionFloat.sum(
                regrets[information_set],
                extensive_game.ActionFloat(immediate_regrets)
            )

        # Update the strategy for the next iteration
        strategy_t_1[information_set] = cfr_util.compute_regret_matching(regrets[information_set])

        return expected_utility
    else:
        # It is the other player. Sample an action and return the value.
        information_set = cfr_game.get_information_set(game, node)
        if information_set not in strategy_t.get_info_sets():
            strategy_t.set_uniform_action_probs(information_set, list(node.children.keys()))

        a = cfr_game.sample_action(strategy_t[information_set])
        return external_sampling_cfr_recursive(
            game,
            node.children[a],
            player,
            regrets,
            strategy_t,
            strategy_t_1)