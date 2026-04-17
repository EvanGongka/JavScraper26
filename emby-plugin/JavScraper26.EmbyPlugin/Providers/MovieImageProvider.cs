using JavScraper26.EmbyPlugin.Extensions;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Configuration;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.Logging;
using MediaBrowser.Model.Providers;

namespace JavScraper26.EmbyPlugin.Providers;

public class MovieImageProvider : BaseProvider, IRemoteImageProvider, IHasOrder
{
    public MovieImageProvider(ILogManager logManager) : base(logManager.GetLogger(nameof(MovieImageProvider)))
    {
    }

    public async Task<IEnumerable<RemoteImageInfo>> GetImages(BaseItem item, LibraryOptions libraryOptions, CancellationToken cancellationToken)
    {
        await Task.CompletedTask.ConfigureAwait(false);

        var pid = item.GetPid(Plugin.ProviderId);
        if (string.IsNullOrWhiteSpace(pid.Provider) || string.IsNullOrWhiteSpace(pid.Id))
        {
            return Enumerable.Empty<RemoteImageInfo>();
        }

        return new[]
        {
            new RemoteImageInfo
            {
                ProviderName = Plugin.ProviderName,
                Type = ImageType.Primary,
                Url = ApiClient.GetImageApiUrl("primary", pid.Provider, pid.Id),
            },
            new RemoteImageInfo
            {
                ProviderName = Plugin.ProviderName,
                Type = ImageType.Thumb,
                Url = ApiClient.GetImageApiUrl("thumb", pid.Provider, pid.Id),
            },
            new RemoteImageInfo
            {
                ProviderName = Plugin.ProviderName,
                Type = ImageType.Backdrop,
                Url = ApiClient.GetImageApiUrl("backdrop", pid.Provider, pid.Id),
            },
        };
    }

    public bool Supports(BaseItem item)
    {
        return item is Movie;
    }

    public IEnumerable<ImageType> GetSupportedImages(BaseItem item)
    {
        return new[]
        {
            ImageType.Primary,
            ImageType.Thumb,
            ImageType.Backdrop,
        };
    }
}
