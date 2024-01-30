import argparse
import os

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import stan

import models


def stan_map(vector):
    """ Create a map of vector items : id. """
    unique_items = np.unique(vector)
    return {item: id_ for id_, item in enumerate(unique_items, start=1)}


def read_data(fname):
    """ Read football-data.co.uk csv """
    data = (
        pd.read_csv(fname)
        .rename(columns={
                'HomeTeam': 'home_team',
                'AwayTeam': 'away_team',
                'FTHG': 'home_goals',
                'FTAG': 'away_goals'
            })
        .loc[lambda df: ~pd.isnull(df['home_goals'])]  # Remove future games
    )

    team_map = stan_map(pd.concat([data['home_team'], data['away_team']]))
    data['home_team_id'] = data['home_team'].replace(team_map)
    data['away_team_id'] = data['away_team'].replace(team_map)


    for col in ('home_goals', 'away_goals'):
        data[col] = [int(c) for c in data[col]]

    return data, team_map


def fit_model(data, team_map, model, use_cache, **kwargs):
    """
    Fit a Stan model and return the output.

    Arguments:
     * data      -- Data containing football scores : pd.DataFrame
     * team_map  -- name to id mapping : Dict
     * model     -- Model to be fit : model.SoccerModel
     * use_cache -- Whether the compiled Stan model should be loaded
                    from/saved to file : Bool

    Keyword arguments are passed to stan.StanModel.sampling
    """
    model_data = {
        'n_teams': len(team_map),
        'n_games': len(data),
        'home_team': data['home_team_id'].to_list(),
        'away_team': data['away_team_id'].to_list(),
        'home_goals': data['home_goals'].to_list(),
        'away_goals': data['away_goals'].to_list()
    }

    with open(model.modelfile, "rt") as infile:
        stan_program = infile.read()

    if use_cache:
        cache_file = os.path.join(os.path.dirname(__file__),
                                  '../cache/{0}.pkl'.format(model.name))
        try:
            stan_model = joblib.load(cache_file)
        except FileNotFoundError:
            stan_model = stan.build(program_code=stan_program, data=model_data)
            joblib.dump(stan_model, cache_file)
    else:
        stan_model = stan.build(program_code=stan_program, data=model_data)

    fit = stan_model.sample(data=model_data, **kwargs)
    output = fit.extract()

    # Tidy the output a little...
    reverse_map = {v: k for k, v in team_map.items()}
    for param in model.team_parameters:
        df = pd.DataFrame(output[param])
        df.columns = [reverse_map[id_ + 1] for id_ in df.columns]
        output[param] = df

    return output


def plot_output(model, output):
    """ Plot parameters from Stan output and save to file. """
    for param in model.parameters:
        fig = plot_parameter(output[param], param, 'dimgray')
        fig.savefig('{0}/../figures/{1}-{2}.png'.format(
            os.path.dirname(os.path.realpath(__file__)), model.name, param))

    for param in model.team_parameters:
        fig = plot_team_parameter(output[param], param, 0.05, 'dimgray')
        fig.savefig('{0}/../figures/{1}-{2}.png'.format(
            os.path.dirname(os.path.realpath(__file__)), model.name, param))


def plot_parameter(data, title, alpha=0.05, axes_colour='dimgray'):
    """ Plot 1-dimensional parameters. """
    fig, ax = plt.subplots(figsize=(8, 6))

    ax.hist(data, bins=50, normed=True, color='black', edgecolor='None')

    # Add title
    fig.suptitle(title, fontsize=16, color=axes_colour)
    # Add axis labels
    ax.set_xlabel('', fontsize=16, color=axes_colour)
    ax.set_ylabel('', fontsize=16, color=axes_colour)

    # Change axes colour
    ax.spines["bottom"].set_color(axes_colour)
    ax.spines["left"].set_color(axes_colour)
    ax.tick_params(colors=axes_colour)
    # Remove top and bottom spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    # Remove extra ticks
    ax.get_xaxis().tick_bottom()
    ax.get_yaxis().tick_left()

    return fig


def plot_team_parameter(data, title, alpha=0.05, axes_colour='dimgray'):
    """ Plot 2-dimensional parameters (i.e. a parameter for each team). """
    fig, ax = plt.subplots(figsize=(8, 6))

    upper = 1 - (alpha / 2)
    lower = 0 + (alpha / 2)

    # Sort by median values
    ordered_teams = data.median().sort_values().keys()

    for i, team in enumerate(ordered_teams):
        x_mean = np.median(data[team])
        x_lower = np.percentile(data[team], lower * 100)
        x_upper = np.percentile(data[team], upper * 100)

        ax.scatter(x_mean, i, alpha=1, color='black', s=25)
        ax.hlines(i, x_lower, x_upper, color='black')

    ax.set_ylim([-1, len(ordered_teams)])
    ax.set_yticks(list(range(len(ordered_teams))))
    ax.set_yticklabels(list(ordered_teams))

    # Add title
    fig.suptitle(title, ha='left', x=0.125, fontsize=18, color='k')

    # Change axes colour
    ax.spines["bottom"].set_color(axes_colour)
    ax.spines["left"].set_color(axes_colour)
    ax.tick_params(colors=axes_colour)

    # Remove top and bottom spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    return fig


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('data', help='Location of file containing match data')
    parser.add_argument('model', help='Name of the model to be used')
    parser.add_argument('--cache', help='Use cache to load/save compiled Stan model',
                        action='store_true')
    parser.add_argument('--chains', help='Number of chains in Stan model',
                        default=4, type=int)
    parser.add_argument('--iter', help='Number of iterations in Stan model',
                        default=2000, type=int)
    args = parser.parse_args()

    data, team_map = read_data(args.data)
    model = models.model_map[args.model]

    output = fit_model(
        data,
        team_map,
        model,
        args.cache,
        iter=args.iter,
        chains=args.chains
    )

    plot_output(model, output)
