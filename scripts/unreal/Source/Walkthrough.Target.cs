using UnrealBuildTool;

public class WalkthroughTarget : TargetRules
{
	public WalkthroughTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("Walkthrough");
	}
}
