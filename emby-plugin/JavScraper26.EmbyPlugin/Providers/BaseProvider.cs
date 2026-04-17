using MediaBrowser.Common.Net;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Logging;

namespace JavScraper26.EmbyPlugin.Providers;

public abstract class BaseProvider : IHasSupportedExternalIdentifiers
{
    protected readonly ILogger Logger;

    protected BaseProvider(ILogger logger)
    {
        Logger = logger;
    }

    public virtual string Name => Plugin.ProviderName;

    public virtual int Order => 1;

    public string[] GetSupportedExternalIdentifiers()
    {
        return new[] { Plugin.ProviderName };
    }

    public Task<HttpResponseInfo> GetImageResponse(string url, CancellationToken cancellationToken)
    {
        Logger.Debug("GetImageResponse: {0}", url);
        return ApiClient.GetImageResponse(url, cancellationToken);
    }
}
