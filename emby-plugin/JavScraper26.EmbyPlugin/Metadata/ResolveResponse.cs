using System.Text.Json.Serialization;

namespace JavScraper26.EmbyPlugin.Metadata;

public class ResolveResponse
{
    [JsonPropertyName("results")]
    public List<ResolvedMovie> Results { get; set; } = new();
}
