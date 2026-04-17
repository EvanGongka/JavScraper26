using System.Text.Json.Serialization;

namespace JavScraper26.EmbyPlugin.Metadata;

public class ResolvedMovie
{
    [JsonPropertyName("provider")]
    public string Provider { get; set; } = string.Empty;

    [JsonPropertyName("providerItemId")]
    public string ProviderItemId { get; set; } = string.Empty;

    [JsonPropertyName("number")]
    public string Number { get; set; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("originalTitle")]
    public string OriginalTitle { get; set; } = string.Empty;

    [JsonPropertyName("summary")]
    public string Summary { get; set; } = string.Empty;

    [JsonPropertyName("releaseDate")]
    public string ReleaseDate { get; set; } = string.Empty;

    [JsonPropertyName("durationMinutes")]
    public string DurationMinutes { get; set; } = string.Empty;

    [JsonPropertyName("director")]
    public string Director { get; set; } = string.Empty;

    [JsonPropertyName("maker")]
    public string Maker { get; set; } = string.Empty;

    [JsonPropertyName("publisher")]
    public string Publisher { get; set; } = string.Empty;

    [JsonPropertyName("series")]
    public string Series { get; set; } = string.Empty;

    [JsonPropertyName("score")]
    public string Score { get; set; } = string.Empty;

    [JsonPropertyName("actors")]
    public string[] Actors { get; set; } = Array.Empty<string>();

    [JsonPropertyName("genres")]
    public string[] Genres { get; set; } = Array.Empty<string>();

    [JsonPropertyName("coverUrl")]
    public string CoverUrl { get; set; } = string.Empty;

    [JsonPropertyName("thumbUrl")]
    public string ThumbUrl { get; set; } = string.Empty;

    [JsonPropertyName("previewImages")]
    public string[] PreviewImages { get; set; } = Array.Empty<string>();

    [JsonPropertyName("trailerUrl")]
    public string TrailerUrl { get; set; } = string.Empty;

    [JsonPropertyName("detailUrl")]
    public string DetailUrl { get; set; } = string.Empty;
}
