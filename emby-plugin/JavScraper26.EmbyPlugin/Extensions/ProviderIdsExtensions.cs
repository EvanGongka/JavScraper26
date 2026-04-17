using JavScraper26.EmbyPlugin.Helpers;
using MediaBrowser.Model.Entities;

namespace JavScraper26.EmbyPlugin.Extensions;

public static class ProviderIdsExtensions
{
    public static ProviderId GetPid(this IHasProviderIds instance, string name)
    {
        return ProviderId.Parse(instance.GetProviderId(name));
    }

    public static void SetPid(this IHasProviderIds instance, string name, string provider, string id)
    {
        instance.SetProviderId(name, new ProviderId
        {
            Provider = provider,
            Id = id,
        }.ToString());
    }
}
