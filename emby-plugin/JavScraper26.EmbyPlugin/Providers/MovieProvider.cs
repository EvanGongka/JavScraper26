using JavScraper26.EmbyPlugin.Extensions;
using JavScraper26.EmbyPlugin.Metadata;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Configuration;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.Logging;
using MediaBrowser.Model.Providers;
using MovieLookupInfo = MediaBrowser.Controller.Providers.MovieInfo;

namespace JavScraper26.EmbyPlugin.Providers;

public class MovieProvider : BaseProvider, IRemoteMetadataProvider<Movie, MovieLookupInfo>, IHasOrder, IHasMetadataFeatures
{
    public MovieProvider(ILogManager logManager) : base(logManager.GetLogger(nameof(MovieProvider)))
    {
    }

    public MetadataFeatures[] Features => new[]
    {
        MetadataFeatures.Collections,
        MetadataFeatures.Adult,
        MetadataFeatures.RequiredSetup,
    };

    public async Task<IEnumerable<RemoteSearchResult>> GetSearchResults(MovieLookupInfo info, CancellationToken cancellationToken)
    {
        var results = await ApiClient.ResolveMovieAsync(info.Name ?? string.Empty, info.Path ?? string.Empty, info.Year, cancellationToken)
            .ConfigureAwait(false);

        return results.Results.Select(ToSearchResult).ToList();
    }

    public async Task<MetadataResult<Movie>> GetMetadata(MovieLookupInfo info, CancellationToken cancellationToken)
    {
        var pid = info.GetPid(Plugin.ProviderId);
        ResolvedMovie? movie = null;

        if (!string.IsNullOrWhiteSpace(pid.Provider) && !string.IsNullOrWhiteSpace(pid.Id))
        {
            movie = await ApiClient.GetMovieAsync(pid.Provider, pid.Id, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            movie = (await ApiClient.ResolveMovieAsync(info.Name ?? string.Empty, info.Path ?? string.Empty, info.Year, cancellationToken)
                .ConfigureAwait(false)).Results.FirstOrDefault();
        }

        if (movie == null)
        {
            return new MetadataResult<Movie> { HasMetadata = false };
        }

        var result = new MetadataResult<Movie>
        {
            Item = new Movie
            {
                Name = string.IsNullOrWhiteSpace(movie.Title) ? movie.Number : movie.Title,
                OriginalTitle = string.IsNullOrWhiteSpace(movie.OriginalTitle) ? movie.Title : movie.OriginalTitle,
                Overview = movie.Summary,
                OfficialRating = "JP-18+",
                PremiereDate = ParseDate(movie.ReleaseDate),
                ProductionYear = ParseYear(movie.ReleaseDate),
                Genres = movie.Genres ?? Array.Empty<string>(),
            },
            HasMetadata = true,
        };

        result.Item.SetPid(Plugin.ProviderId, movie.Provider, movie.ProviderItemId);

        if (!string.IsNullOrWhiteSpace(movie.Maker))
        {
            result.Item.AddStudio(movie.Maker);
        }

        if (!string.IsNullOrWhiteSpace(movie.Series))
        {
            result.Item.AddCollection(movie.Series);
        }

        if (!string.IsNullOrWhiteSpace(movie.Director))
        {
            result.AddPerson(new PersonInfo
            {
                Name = movie.Director,
                Type = PersonType.Director,
            });
        }

        foreach (var actor in movie.Actors ?? Array.Empty<string>())
        {
            if (string.IsNullOrWhiteSpace(actor))
            {
                continue;
            }

            result.AddPerson(new PersonInfo
            {
                Name = actor,
                Type = PersonType.Actor,
            });
        }

        return result;
    }

    private RemoteSearchResult ToSearchResult(ResolvedMovie movie)
    {
        var result = new RemoteSearchResult
        {
            Name = $"[{movie.Provider}] {movie.Number} {movie.Title}".Trim(),
            SearchProviderName = Plugin.ProviderName,
            PremiereDate = ParseDate(movie.ReleaseDate),
            ProductionYear = ParseYear(movie.ReleaseDate),
            ImageUrl = ApiClient.GetImageApiUrl("primary", movie.Provider, movie.ProviderItemId),
        };
        result.SetPid(Plugin.ProviderId, movie.Provider, movie.ProviderItemId);
        return result;
    }

    private static DateTime? ParseDate(string? raw)
    {
        if (DateTime.TryParse(raw, out var parsed))
        {
            return parsed;
        }
        return null;
    }

    private static int? ParseYear(string? raw)
    {
        return ParseDate(raw)?.Year;
    }
}
