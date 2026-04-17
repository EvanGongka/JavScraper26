namespace JavScraper26.EmbyPlugin.Helpers;

public class ProviderId
{
    public string Provider { get; set; } = string.Empty;

    public string Id { get; set; } = string.Empty;

    public static ProviderId Parse(string? rawPid)
    {
        var values = rawPid?.Split(':');
        return new ProviderId
        {
            Provider = values?.Length > 0 ? values[0] : string.Empty,
            Id = values?.Length > 1 ? Uri.UnescapeDataString(values[1]) : string.Empty,
        };
    }

    public override string ToString()
    {
        return $"{Provider}:{Uri.EscapeDataString(Id)}";
    }
}
