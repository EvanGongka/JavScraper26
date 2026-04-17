using System.Collections.Specialized;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using JavScraper26.EmbyPlugin.Configuration;
using JavScraper26.EmbyPlugin.Metadata;
using MediaBrowser.Common.Net;

namespace JavScraper26.EmbyPlugin;

public static class ApiClient
{
    private static readonly HttpClient HttpClient = new();

    private static PluginConfiguration Configuration => Plugin.Instance.Configuration;

    private static string ComposeUrl(string path, NameValueCollection nv)
    {
        var builder = new UriBuilder(Configuration.ServerUrl)
        {
            Path = path.TrimStart('/'),
            Query = string.Join("&", nv.AllKeys
                .Where(k => !string.IsNullOrWhiteSpace(k))
                .SelectMany(k => nv.GetValues(k)!.Select(v => $"{Uri.EscapeDataString(k!)}={Uri.EscapeDataString(v ?? string.Empty)}")))
        };
        return builder.ToString();
    }

    private static NameValueCollection ProxyQuery()
    {
        var nv = new NameValueCollection
        {
            { "proxyEnabled", Configuration.EnableProxy.ToString().ToLowerInvariant() },
            { "proxyProtocol", Configuration.ProxyProtocol ?? string.Empty },
            { "proxyHost", Configuration.ProxyHost ?? string.Empty },
            { "proxyPort", Configuration.ProxyPort ?? string.Empty },
        };
        return nv;
    }

    public static string GetImageApiUrl(string imageType, string provider, string id)
    {
        return ComposeUrl($"/emby-api/v1/images/{imageType}/{provider}/{id}", ProxyQuery());
    }

    public static async Task<ResolveResponse> ResolveMovieAsync(string name, string path, int? year, CancellationToken cancellationToken)
    {
        var nv = ProxyQuery();
        if (!string.IsNullOrWhiteSpace(name)) nv.Add("name", name);
        if (!string.IsNullOrWhiteSpace(path)) nv.Add("path", path);
        if (year.HasValue) nv.Add("year", year.Value.ToString());
        var url = ComposeUrl("/emby-api/v1/movies/resolve", nv);
        return await GetJsonAsync<ResolveResponse>(url, cancellationToken).ConfigureAwait(false);
    }

    public static async Task<ResolvedMovie> GetMovieAsync(string provider, string id, CancellationToken cancellationToken)
    {
        var url = ComposeUrl($"/emby-api/v1/movies/{provider}/{id}", ProxyQuery());
        return await GetJsonAsync<ResolvedMovie>(url, cancellationToken).ConfigureAwait(false);
    }

    public static async Task<HttpResponseInfo> GetImageResponse(string url, CancellationToken cancellationToken)
    {
        var request = new HttpRequestMessage(HttpMethod.Get, url);
        request.Headers.Add("User-Agent", DefaultUserAgent);
        var response = await HttpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        return new HttpResponseInfo
        {
            Content = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false),
            ContentLength = response.Content.Headers.ContentLength,
            ContentType = response.Content.Headers.ContentType?.ToString(),
            StatusCode = response.StatusCode,
            Headers = response.Content.Headers.ToDictionary(kvp => kvp.Key, kvp => string.Join(", ", kvp.Value))
        };
    }

    private static async Task<T> GetJsonAsync<T>(string url, CancellationToken cancellationToken)
    {
        var request = new HttpRequestMessage(HttpMethod.Get, url);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.Add("User-Agent", DefaultUserAgent);
        var response = await HttpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        var payload = await response.Content.ReadFromJsonAsync<T>(cancellationToken: cancellationToken).ConfigureAwait(false);
        if (payload == null)
        {
            throw new InvalidOperationException("Backend returned an empty JSON payload.");
        }
        return payload;
    }

    private static string DefaultUserAgent => $"{Plugin.ProviderName}/{Plugin.Instance.Version}";
}
