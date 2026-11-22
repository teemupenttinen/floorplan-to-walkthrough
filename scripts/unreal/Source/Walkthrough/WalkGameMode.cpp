#include "WalkGameMode.h"
#include "WalkCharacter.h"

AWalkGameMode::AWalkGameMode()
{
	DefaultPawnClass = AWalkCharacter::StaticClass();
}
