import functools

import gymnasium
import numpy as np
import pygame
from gymnasium.spaces import Discrete, MultiDiscrete
from pettingzoo import ParallelEnv
from scipy.stats import levy_stable


class SurgeryQuotaScheduler(ParallelEnv):
    metadata = {'render_modes': ['human', 'terminal'],
                'name': 'sqsc_v1'}

    def __init__(self, render_mode=None, max_agents=12, max_days=7, max_episode_length=7):
        self.max_agents = max_agents
        self.max_days = max_days
        self.max_episode_length = max_episode_length
        self.possible_agents = ["agent_" + str(r) for r in range(self.max_agents)]
        self.agent_name_mapping = dict(zip(self.possible_agents, list(range(len(self.possible_agents)))))
        self.agent_action_mapping = {0: 1, 1: -1, 2: 0}
        self.render_mode = render_mode

    @functools.lru_cache(maxsize=None)
    def observation_space(self, agent):
        return MultiDiscrete([3, 2, 2, self.max_days, *[self.max_agents + 2 for _ in range(self.max_days)]],
                             start=[1, 0, 0, 0, *[-1 for _ in range(self.max_days)]])

    @functools.lru_cache(maxsize=None)
    def action_space(self, agent):
        return Discrete(3)

    def render(self):
        if self.render_mode == "human":
            pygame.init()
            win_width, win_height = 1000, 600
            win = pygame.display.set_mode((win_width, win_height))
            pygame.display.set_caption("Surgery Quota Scheduler")
            run = True
            while run:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        run = False
                win.fill((255, 255, 255))
                font = pygame.font.Font(None, 36)
                y = 50
                for agent, pos in {agent: self.agents_data[agent]['position'] for agent in self.agents}.items():
                    text = font.render(f"{agent}: Day {pos + 1}", True, (0, 0, 0))
                    win.blit(text, (50, y))
                    y += 30
                pygame.display.flip()
            pygame.quit()
        elif self.render_mode == 'terminal':
            return self.observed_state
        else:
            gymnasium.logger.warn('You are calling render mode without specifying any render mode.')
            return

    def close(self):
        if self.render_mode == "human":
            pygame.quit()

    def reset(self, seed=None, options=None):
        self.rng = np.random.default_rng(seed)
        self.num_moves = 0
        self.agents = self.possible_agents[:]
        self.target_state = {day: (boundaries['min'] + boundaries['max']) / 2 for day, boundaries in
                             options['target_state'].items()} if options is not None else {0: 3, 1: 2, 2: 2, 3: 2, 4: 1,
                                                                                           5: 1, 6: 1}
        self.agents_data = options['agents_data'] if options is not None else {agent: {'active': True,
                                                                                       'position': self.rng.integers(0,
                                                                                                                     7,
                                                                                                                     1).item(),
                                                                                       'base_reward': 1.0,
                                                                                       'window': 5,
                                                                                       'alpha': 2.0,
                                                                                       'urgency': self.rng.integers(1,
                                                                                                                    4,
                                                                                                                    1).item(),
                                                                                       'completeness': self.rng.integers(
                                                                                           0, 2, 1).item(),
                                                                                       'complexity': self.rng.integers(
                                                                                           0, 2, 1).item(),
                                                                                       'mutation_rate': 0.0} for agent
                                                                               in self.agents}
        observations = {agent: np.array([self.agents_data[agent]['urgency'],
                                         self.agents_data[agent]['completeness'],
                                         self.agents_data[agent]['complexity'],
                                         self.agents_data[agent]['position'],
                                         *[self.observed_state[day] if day in [int((self.agents_data[agent][
                                                                                        'position'] + np.ceil(
                                             d - self.agents_data[agent]['window'] / 2)) % self.max_days) for d in
                                                                               range(self.agents_data[agent][
                                                                                         'window'])] else -1 for day in
                                           self.observed_state]])
                        for agent in self.agents}
        infos = {agent: self.agents_data[agent] for agent in self.agents}
        return observations, infos

    def step(self, actions):
        if not actions:
            return {}, {}, {}, {}, {}
        self.num_moves += 1
        for agent in self.agents:
            if self.agents_data[agent]['active']:
                self.agents_data[agent]['position'] = (self.agents_data[agent]['position'] + self.agent_action_mapping[
                    int(actions[agent])]) % self.max_days
                if self.agents_data[agent]['position'] > (self.max_days // 2):
                    if int(actions[agent]) == 0:
                        if self.agents_data[agent]['mutation_rate'] != 1.0:
                            self.agents_data[agent]['mutation_rate'] = min(
                                self.agents_data[agent]['mutation_rate'] + 0.05, 1.0)
                    elif int(actions[agent]) == 1:
                        if self.agents_data[agent]['mutation_rate'] != 0.0:
                            self.agents_data[agent]['mutation_rate'] = max(
                                self.agents_data[agent]['mutation_rate'] - 0.05, 0.0)
        rewards = {agent: self.reward_map(agent) for agent in self.agents}
        terminations = {agent: list(actions.values()).count(2) > self.max_agents * 0.8 for agent in self.agents}
        truncations = {agent: self.num_moves >= self.max_episode_length for agent in self.agents}
        if any(terminations.values()) or any(truncations.values()):
            rewards = {agent: r - 0.5 * abs(
                self.observed_state[self.agents_data[agent]['position']] - self.target_state[
                    self.agents_data[agent]['position']]) for agent, r in rewards.items()}
        observations = {agent: np.array([self.agents_data[agent]['urgency'],
                                         self.agents_data[agent]['completeness'],
                                         self.agents_data[agent]['complexity'],
                                         self.agents_data[agent]['position'],
                                         *[self.observed_state[day] if day in [int((self.agents_data[agent][
                                                                                        'position'] + np.ceil(
                                             d - self.agents_data[agent]['window'] / 2)) % self.max_days) for d in
                                                                               range(self.agents_data[agent][
                                                                                         'window'])] else -1 for day in
                                           self.observed_state]])
                        for agent in self.agents}
        infos = {agent: self.agents_data[agent] for agent in self.agents}
        return observations, rewards, terminations, truncations, infos

    @property
    def observed_state(self):
        return {day: [self.agents_data[agent]['position'] for agent in self.agents].count(day) for day in
                range(self.max_days)}

    def reward_map(self, agent):
        discrepancy = {day: abs(self.observed_state[day] - self.target_state[day]) for day in self.target_state}
        window = [int((self.agents_data[agent]['position'] + np.ceil(
            d - self.agents_data[agent]['window'] / 2)) % self.max_days) for d in
                  range(self.agents_data[agent]['window'])]
        masked_discrepancy = {day: discrepancy[day] if day in window else 0 for day in discrepancy}
        rv = levy_stable(self.agents_data[agent]['alpha'], 0.0, loc=self.agents_data[agent]['position'], scale=1.0)
        weighted_discrepancy_sum = np.sum([rv.pdf(day) * masked_discrepancy[day] for day in masked_discrepancy])

        global_discrepancy = sum(discrepancy.values())

        reward = - (weighted_discrepancy_sum + 0.05 * global_discrepancy) * self.agents_data[agent]['base_reward'] / 2

        current_day = self.agents_data[agent]['position']
        if self.observed_state[current_day] < self.target_state[current_day]:
            reward += 0.5 * self.agents_data[agent]['base_reward']

        if self.observed_state[current_day] > self.target_state[current_day]:
            reward -= 0.1 * self.agents_data[agent]['base_reward']

        scale = max(1, (self.agents_data[agent]['complexity'] + (1 - self.agents_data[agent]['completeness'])) *
                    self.agents_data[agent]['urgency'])
        if scale > 3:
            reward -= (self.agents_data[agent]['position'] - 1) / 5

        return reward
