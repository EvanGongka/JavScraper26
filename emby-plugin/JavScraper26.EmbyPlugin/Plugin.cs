using JavScraper26.EmbyPlugin.Configuration;
using MediaBrowser.Common;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Controller.Plugins;

namespace JavScraper26.EmbyPlugin;

public class Plugin : BasePluginSimpleUI<PluginConfiguration>
{
    public Plugin(IApplicationHost applicationHost) : base(applicationHost)
    {
        Instance = this;
    }

    public const string ProviderName = "javScraper26";
    public const string ProviderId = "javScraper26";

    public static Plugin Instance { get; private set; } = null!;

    public override string Name => ProviderName;

    public override string Description => "Use javScraper26 service mode as an Emby movie metadata provider.";

    public override Guid Id => Guid.Parse("dff66b47-0b46-4ea4-bf85-6d59b18e4956");

    public PluginConfiguration Configuration => GetOptions();
}
