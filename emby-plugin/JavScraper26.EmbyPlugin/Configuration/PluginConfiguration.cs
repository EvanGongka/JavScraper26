using System.ComponentModel;
using Emby.Web.GenericEdit;
using MediaBrowser.Model.Attributes;

namespace JavScraper26.EmbyPlugin.Configuration;

public class PluginConfiguration : EditableOptionsBase
{
    public override string EditorTitle => Plugin.ProviderName;

    [DisplayName("Server URL")]
    [Description("Full base URL of the javScraper26 service mode backend, for example http://127.0.0.1:8765")]
    [Required]
    public string ServerUrl { get; set; } = "http://127.0.0.1:8765";

    [DisplayName("Enable Proxy")]
    [Description("When enabled, all metadata and image requests append proxy parameters to the backend API.")]
    public bool EnableProxy { get; set; }

    [DisplayName("Proxy Protocol")]
    [VisibleCondition(nameof(EnableProxy), ValueCondition.IsEqual, true)]
    public string ProxyProtocol { get; set; } = "http";

    [DisplayName("Proxy Host")]
    [VisibleCondition(nameof(EnableProxy), ValueCondition.IsEqual, true)]
    public string ProxyHost { get; set; } = string.Empty;

    [DisplayName("Proxy Port")]
    [VisibleCondition(nameof(EnableProxy), ValueCondition.IsEqual, true)]
    public string ProxyPort { get; set; } = string.Empty;
}
